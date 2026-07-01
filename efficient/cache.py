"""Semantic cache — avoids re-computing similar queries.

Uses embedding similarity to detect when a new query is semantically
identical to a previously cached response. Production hit rates: 20-45%.

Implementation:
- SQLite for persistence (query text, response, embedding, timestamp)
- Cosine similarity on compact embeddings (384-dim from Ollama or hash-based)
- LRU eviction when cache exceeds max_entries
- Per-intent cache namespaces to reduce false positives

The embedding model uses Ollama's /api/embeddings endpoint if available,
falling back to a fast hash-based simhash for zero-dependency operation.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np


@dataclass
class CacheEntry:
    """A cached response."""

    query_hash: str
    query_text: str
    response: str
    embedding: np.ndarray
    model: str
    timestamp: float
    intent: str = ""
    hit_count: int = 0


class SemanticCache:
    """Semantic similarity cache for LLM responses.

    Args:
        db_path: Path to SQLite cache database
        ollama_host: Ollama API URL for embeddings
        similarity_threshold: Cosine similarity threshold for cache hits (0.0-1.0)
        max_entries: Maximum cache entries before LRU eviction
        embedding_model: Ollama model to use for embeddings
        ttl_seconds: Time-to-live for cache entries (0 = no expiry)

    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_hash TEXT UNIQUE NOT NULL,
        query_text TEXT NOT NULL,
        response TEXT NOT NULL,
        embedding BLOB NOT NULL,
        model TEXT NOT NULL,
        timestamp REAL NOT NULL,
        intent TEXT DEFAULT '',
        hit_count INTEGER DEFAULT 0,
        last_accessed REAL NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_intent ON cache(intent);
    CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache(last_accessed);
    """

    def __init__(
        self,
        db_path: str = "",
        ollama_host: str = "http://localhost:11434",
        similarity_threshold: float = 0.92,
        max_entries: int = 10000,
        embedding_model: str = "nomic-embed-text",
        ttl_seconds: float = 0,
    ):
        if not db_path:
            db_path = str(Path.home() / ".efficient" / "cache.db")
        self.db_path = db_path
        self.ollama_host = ollama_host
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self.embedding_model = embedding_model
        self.ttl_seconds = ttl_seconds
        self._embedding_dim = 384  # default for nomic-embed-text

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(self.SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── Embedding ─────────────────────────────────────────────────────────

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text. Tries Ollama first, falls back to hash-based.
        """
        # Try Ollama embeddings
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{self.ollama_host}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": text},
                )
                if resp.status_code == 200:
                    emb = np.array(resp.json().get("embedding", []), dtype=np.float32)
                    if len(emb) > 0:
                        self._embedding_dim = len(emb)
                        return self._normalize(emb)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            pass

        # Fallback: hash-based embedding (deterministic, fast, no dependencies)
        return self._hash_embedding(text)

    def _hash_embedding(self, text: str, dim: int = 384) -> np.ndarray:
        """Fast hash-based embedding for zero-dependency operation.
        Not as good as real embeddings, but catches exact and near-duplicate matches.
        """
        emb = np.zeros(dim, dtype=np.float32)
        # Use character n-grams to create a pseudo-embedding
        tokens = text.lower().split()
        for token in tokens:
            for n in (1, 2, 3):
                grams = [token[i:i+n] for i in range(len(token) - n + 1)] if len(token) >= n else [token]
                for gram in grams:
                    h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                    idx = h % dim
                    emb[idx] += 1.0
        return self._normalize(emb)

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        """L2 normalize a vector."""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two normalized vectors."""
        return float(np.dot(a, b))

    # ─── Public API ─────────────────────────────────────────────────────────

    def get(self, query: str, intent: str = "") -> CacheEntry | None:
        """Look up a query in the cache.

        Returns CacheEntry if a semantically similar query is found,
        None otherwise.
        """
        query_embedding = self._get_embedding(query)

        with self._conn() as conn:
            # Filter by intent if specified (reduces false positives)
            if intent:
                rows = conn.execute(
                    "SELECT * FROM cache WHERE intent = ? ORDER BY last_accessed DESC LIMIT 500",
                    (intent,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cache ORDER BY last_accessed DESC LIMIT 500",
                ).fetchall()

            best_score = 0.0
            best_row = None

            for row in rows:
                # Check TTL
                if self.ttl_seconds > 0 and time.time() - row["timestamp"] > self.ttl_seconds:
                    continue

                cached_emb = np.frombuffer(row["embedding"], dtype=np.float32)
                score = self._cosine_similarity(query_embedding, cached_emb)

                if score > best_score:
                    best_score = score
                    best_row = row

            if best_row is not None and best_score >= self.similarity_threshold:
                # Update hit count and last accessed
                conn.execute(
                    "UPDATE cache SET hit_count = hit_count + 1, last_accessed = ? WHERE id = ?",
                    (time.time(), best_row["id"]),
                )

                return CacheEntry(
                    query_hash=best_row["query_hash"],
                    query_text=best_row["query_text"],
                    response=best_row["response"],
                    embedding=np.frombuffer(best_row["embedding"], dtype=np.float32),
                    model=best_row["model"],
                    timestamp=best_row["timestamp"],
                    intent=best_row["intent"],
                    hit_count=best_row["hit_count"] + 1,
                )

        return None

    def put(
        self,
        query: str,
        response: str,
        model: str,
        intent: str = "",
    ) -> None:
        """Store a query-response pair in the cache."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        embedding = self._get_embedding(query)

        with self._conn() as conn:
            # Upsert (replace if exists)
            conn.execute(
                """INSERT OR REPLACE INTO cache
                   (query_hash, query_text, response, embedding, model, timestamp, intent, hit_count, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    query_hash,
                    query,
                    response,
                    embedding.tobytes(),
                    model,
                    time.time(),
                    intent,
                    time.time(),
                ),
            )

        # Evict if over capacity
        self._evict()

    def _evict(self) -> None:
        """LRU eviction when cache exceeds max_entries."""
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) as n FROM cache").fetchone()["n"]
            if count > self.max_entries:
                excess = count - self.max_entries
                conn.execute(
                    "DELETE FROM cache WHERE id IN ("
                    "  SELECT id FROM cache ORDER BY last_accessed ASC LIMIT ?"
                    ")",
                    (excess,),
                )

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._conn() as conn:
            conn.execute("DELETE FROM cache")

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as total, SUM(hit_count) as total_hits FROM cache",
            ).fetchone()
            return {
                "total_entries": row["total"] or 0,
                "total_hits": row["total_hits"] or 0,
                "db_size_bytes": Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0,
            }
