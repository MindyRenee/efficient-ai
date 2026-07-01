"""
Tests for the semantic cache module.
"""

import os
import tempfile
import pytest
from efficient.cache import SemanticCache


@pytest.fixture
def cache(tmp_path):
    """Create a temporary cache instance."""
    db = str(tmp_path / "test_cache.db")
    return SemanticCache(
        db_path=db,
        ollama_host="http://localhost:99999",  # Force hash-based embeddings
        similarity_threshold=0.85,
    )


class TestSemanticCache:
    def test_put_and_get_exact(self, cache):
        """Exact same query should be retrieved from cache."""
        cache.put("What is Python?", "Python is a programming language.", "qwen2.5:7b", "simple_qa")
        result = cache.get("What is Python?", intent="simple_qa")
        assert result is not None
        assert result.response == "Python is a programming language."
        assert result.model == "qwen2.5:7b"
        assert result.hit_count == 1

    def test_miss_on_different_query(self, cache):
        """Completely different queries should not match."""
        cache.put("What is Python?", "Python is a programming language.", "qwen2.5:7b")
        result = cache.get("What is the capital of France?")
        assert result is None

    def test_hit_on_similar_query(self, cache):
        """Semantically similar queries should match (hash-based)."""
        cache.put("Extract the email from this text", "john@example.com", "phi3:mini", "extraction")
        # Very similar wording — should hit with hash-based embeddings
        result = cache.get("Extract the email from this text", intent="extraction")
        assert result is not None
        assert result.response == "john@example.com"

    def test_intent_filtering(self, cache):
        """Cache should filter by intent namespace."""
        cache.put("Classify this", "positive", "phi3:mini", "classification")
        # Same text but different intent — should not match
        result = cache.get("Classify this", intent="extraction")
        assert result is None
        # Same intent — should match
        result = cache.get("Classify this", intent="classification")
        assert result is not None

    def test_hit_count_increments(self, cache):
        """Hit count should increment on each cache hit."""
        cache.put("test query", "test response", "qwen2.5:7b")
        cache.get("test query")
        cache.get("test query")
        cache.get("test query")
        result = cache.get("test query")
        assert result is not None
        assert result.hit_count == 4

    def test_clear(self, cache):
        """Clear should remove all entries."""
        cache.put("query 1", "response 1", "qwen2.5:7b")
        cache.put("query 2", "response 2", "qwen2.5:7b")
        cache.clear()
        assert cache.get("query 1") is None
        assert cache.get("query 2") is None

    def test_stats(self, cache):
        """Stats should return correct counts."""
        cache.put("query 1", "response 1", "qwen2.5:7b")
        cache.put("query 2", "response 2", "qwen2.5:7b")
        cache.get("query 1")
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["total_hits"] == 1

    def test_lru_eviction(self, tmp_path):
        """Cache should evict LRU entries when over capacity."""
        db = str(tmp_path / "test_evict.db")
        cache = SemanticCache(db_path=db, ollama_host="http://localhost:99999", max_entries=3)
        cache.put("q1", "r1", "m")
        cache.put("q2", "r2", "m")
        cache.put("q3", "r3", "m")
        # Access q1 to make it more recently used
        cache.get("q1")
        cache.put("q4", "r4", "m")  # Should evict q2 (least recently accessed)
        assert cache.get("q1") is not None  # Still present
        assert cache.get("q2") is None      # Evicted
