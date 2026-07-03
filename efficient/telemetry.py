"""Telemetry — tracks every inference request, cost, and savings.

Records:
- Which model handled each request
- Token counts (input/output)
- Cost (actual vs. what it would have cost on frontier cloud)
- Latency
- Cache hits/misses
- Local vs. cloud routing decisions

Persists to SQLite at ~/.efficient/telemetry.db.
Generates human-readable reports showing data center demand avoided.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RequestRecord:
    """A single inference request record."""

    timestamp: float = 0.0
    model: str = ""
    provider: str = ""  # ollama, openai, groq, openrouter, etc.
    tier: str = ""  # micro, small, mid, large, frontier
    input_tokens: int = 0
    output_tokens: int = 0
    actual_cost: float = 0.0
    frontier_cost: float = 0.0  # What this would have cost on GPT-5/Claude Opus
    latency_ms: float = 0.0
    cache_hit: bool = False
    local: bool = False
    intent: str = ""  # classified intent
    success: bool = True
    error: str = ""


class Telemetry:
    """SQLite-backed telemetry tracker.

    Usage:
        telemetry = Telemetry()
        telemetry.record(RequestRecord(
            model="qwen2.5:7b", provider="ollama",
            input_tokens=500, output_tokens=200,
            actual_cost=0.0, frontier_cost=0.045,
            local=True, intent="summarization",
        ))
        report = telemetry.report()
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        model TEXT NOT NULL,
        provider TEXT NOT NULL,
        tier TEXT NOT NULL,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        actual_cost REAL DEFAULT 0,
        frontier_cost REAL DEFAULT 0,
        latency_ms REAL DEFAULT 0,
        cache_hit INTEGER DEFAULT 0,
        local INTEGER DEFAULT 0,
        intent TEXT DEFAULT '',
        success INTEGER DEFAULT 1,
        error TEXT DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_timestamp ON requests(timestamp);
    CREATE INDEX IF NOT EXISTS idx_model ON requests(model);
    CREATE INDEX IF NOT EXISTS idx_provider ON requests(provider);
    """

    def __init__(self, db_path: str = ""):
        if not db_path:
            db_path = str(Path.home() / ".efficient" / "telemetry.db")
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(self.SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.commit()
            conn.close()

    def record(self, record: RequestRecord) -> None:
        """Record a single inference request."""
        if record.timestamp == 0.0:
            record.timestamp = time.time()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO requests
                   (timestamp, model, provider, tier, input_tokens, output_tokens,
                    actual_cost, frontier_cost, latency_ms, cache_hit, local,
                    intent, success, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp,
                    record.model,
                    record.provider,
                    record.tier,
                    record.input_tokens,
                    record.output_tokens,
                    record.actual_cost,
                    record.frontier_cost,
                    record.latency_ms,
                    int(record.cache_hit),
                    int(record.local),
                    record.intent,
                    int(record.success),
                    record.error,
                ),
            )

    def total_requests(self, since: float = 0.0) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM requests WHERE timestamp >= ?",
                (since,),
            ).fetchone()
            return int(row["n"])

    def report(self, since_hours: float = 24.0) -> dict:
        """Generate a comprehensive report for the last N hours.

        Returns dict with:
        - total_requests, cache_hits, local_requests, cloud_requests
        - total_tokens, total_actual_cost, total_frontier_cost, total_savings
        - savings_percentage, data_center_queries_avoided
        - model_breakdown, intent_breakdown
        """
        since = time.time() - (since_hours * 3600)

        with self._conn() as conn:
            # Aggregate stats
            row = conn.execute(
                """SELECT
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as cache_hits,
                    SUM(CASE WHEN local = 1 THEN 1 ELSE 0 END) as local_requests,
                    SUM(CASE WHEN local = 0 AND cache_hit = 0 THEN 1 ELSE 0 END) as cloud_requests,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(actual_cost) as total_actual_cost,
                    SUM(frontier_cost) as total_frontier_cost,
                    AVG(latency_ms) as avg_latency_ms
                   FROM requests WHERE timestamp >= ? AND success = 1""",
                (since,),
            ).fetchone()

            total = row["total_requests"] or 0
            cache_hits = row["cache_hits"] or 0
            local = row["local_requests"] or 0
            cloud = row["cloud_requests"] or 0
            actual_cost = row["total_actual_cost"] or 0.0
            frontier_cost = row["total_frontier_cost"] or 0.0
            savings = frontier_cost - actual_cost
            savings_pct = (savings / frontier_cost * 100) if frontier_cost > 0 else 0.0
            data_center_avoided = total - cloud
            avoidance_pct = (data_center_avoided / total * 100) if total > 0 else 0.0

            # Model breakdown
            model_rows = conn.execute(
                """SELECT model, provider, local,
                    COUNT(*) as count,
                    SUM(input_tokens + output_tokens) as tokens,
                    SUM(actual_cost) as cost
                   FROM requests WHERE timestamp >= ? AND success = 1
                   GROUP BY model ORDER BY count DESC""",
                (since,),
            ).fetchall()

            model_breakdown = [
                {
                    "model": r["model"],
                    "provider": r["provider"],
                    "local": bool(r["local"]),
                    "count": r["count"],
                    "tokens": r["tokens"] or 0,
                    "cost": r["cost"] or 0.0,
                }
                for r in model_rows
            ]

            # Intent breakdown
            intent_rows = conn.execute(
                """SELECT intent,
                    COUNT(*) as count,
                    SUM(CASE WHEN local = 1 THEN 1 ELSE 0 END) as local_count,
                    SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) as cache_count
                   FROM requests WHERE timestamp >= ? AND success = 1
                   GROUP BY intent ORDER BY count DESC""",
                (since,),
            ).fetchall()

            intent_breakdown = [
                {
                    "intent": r["intent"] or "unknown",
                    "count": r["count"],
                    "local_count": r["local_count"],
                    "cache_count": r["cache_count"],
                }
                for r in intent_rows
            ]

            return {
                "period_hours": since_hours,
                "total_requests": total,
                "cache_hits": cache_hits,
                "local_requests": local,
                "cloud_requests": cloud,
                "total_input_tokens": row["total_input_tokens"] or 0,
                "total_output_tokens": row["total_output_tokens"] or 0,
                "total_tokens": (row["total_input_tokens"] or 0)
                + (row["total_output_tokens"] or 0),
                "total_actual_cost": actual_cost,
                "total_frontier_cost": frontier_cost,
                "total_savings": savings,
                "savings_percentage": savings_pct,
                "data_center_queries_avoided": data_center_avoided,
                "data_center_avoidance_percentage": avoidance_pct,
                "avg_latency_ms": row["avg_latency_ms"] or 0.0,
                "model_breakdown": model_breakdown,
                "intent_breakdown": intent_breakdown,
            }

    def format_report(self, since_hours: float = 24.0) -> str:
        """Generate a human-readable text report."""
        r = self.report(since_hours)

        if r["total_requests"] == 0:
            return "No requests recorded yet."

        period = (
            f"last {r['period_hours']:.0f}h"
            if r["period_hours"] < 168
            else f"last {r['period_hours'] / 24:.0f}d"
        )

        lines = [
            "",
            "Efficient AI — Impact Report",
            "=" * 60,
            f"Period: {period}",
            "",
            f"  Total requests:          {r['total_requests']:,}",
            f"  Cache hits:              {r['cache_hits']:,} ({r['cache_hits'] / r['total_requests'] * 100:.0f}%)",
            f"  Local inference:         {r['local_requests']:,} ({r['local_requests'] / r['total_requests'] * 100:.0f}%)",
            f"  Cloud (fallback):        {r['cloud_requests']:,} ({r['cloud_requests'] / r['total_requests'] * 100:.0f}%)",
            "",
            f"  Total tokens:            {r['total_tokens']:,}",
            f"  Avg latency:             {r['avg_latency_ms']:.0f}ms",
            "",
            f"  Actual cost:             ${r['total_actual_cost']:.4f}",
            f"  Frontier equivalent:     ${r['total_frontier_cost']:.4f}",
            f"  Total savings:           ${r['total_savings']:.4f} ({r['savings_percentage']:.1f}%)",
            "",
            f"  Data center queries avoided: {r['data_center_queries_avoided']:,} / {r['total_requests']:,}",
            f"  Avoidance rate:              {r['data_center_avoidance_percentage']:.1f}%",
            "",
            "  Model breakdown:",
        ]

        for m in r["model_breakdown"][:10]:
            location = "local" if m["local"] else "cloud"
            lines.append(
                f"    {m['model']:<35} {m['count']:>5}x  {m['tokens']:>8} tok  ${m['cost']:>8.4f}  [{location}]"
            )

        if r["intent_breakdown"]:
            lines.append("")
            lines.append("  Intent breakdown:")
            for i in r["intent_breakdown"][:10]:
                local_pct = (i["local_count"] / i["count"] * 100) if i["count"] > 0 else 0
                cache_pct = (i["cache_count"] / i["count"] * 100) if i["count"] > 0 else 0
                lines.append(
                    f"    {i['intent']:<25} {i['count']:>5}x  (local: {local_pct:.0f}%, cached: {cache_pct:.0f}%)"
                )

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all telemetry data."""
        with self._conn() as conn:
            conn.execute("DELETE FROM requests")
