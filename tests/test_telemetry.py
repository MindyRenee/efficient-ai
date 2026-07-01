"""
Tests for the telemetry module.
"""

import pytest

from efficient.telemetry import RequestRecord, Telemetry


@pytest.fixture
def telemetry(tmp_path):
    """Create a temporary telemetry instance."""
    db = str(tmp_path / "test_telemetry.db")
    return Telemetry(db_path=db)


class TestTelemetry:
    def test_record_and_count(self, telemetry):
        telemetry.record(RequestRecord(
            model="qwen2.5:7b", provider="ollama", tier="SMALL",
            input_tokens=100, output_tokens=50,
            actual_cost=0.0, frontier_cost=0.001,
            local=True, intent="simple_qa",
        ))
        assert telemetry.total_requests() == 1

    def test_report_structure(self, telemetry):
        """Report should return a dict with expected keys."""
        telemetry.record(RequestRecord(
            model="qwen2.5:7b", provider="ollama", tier="SMALL",
            input_tokens=100, output_tokens=50,
            actual_cost=0.0, frontier_cost=0.001,
            local=True, intent="simple_qa",
        ))
        telemetry.record(RequestRecord(
            model="gpt-4o", provider="openai", tier="LARGE",
            input_tokens=200, output_tokens=100,
            actual_cost=0.005, frontier_cost=0.005,
            local=False, intent="reasoning",
        ))
        report = telemetry.report()
        assert report["total_requests"] == 2
        assert report["local_requests"] == 1
        assert report["cloud_requests"] == 1
        assert report["total_actual_cost"] == 0.005
        assert report["total_frontier_cost"] == 0.006
        assert report["total_savings"] == pytest.approx(0.001)
        assert len(report["model_breakdown"]) == 2
        assert len(report["intent_breakdown"]) == 2

    def test_cache_hit_tracking(self, telemetry):
        telemetry.record(RequestRecord(
            model="cache", provider="cache", tier="MICRO",
            cache_hit=True, local=True,
            actual_cost=0.0, frontier_cost=0.002,
        ))
        report = telemetry.report()
        assert report["cache_hits"] == 1
        assert report["data_center_queries_avoided"] == 1  # total(1) - cloud(0)

    def test_format_report(self, telemetry):
        telemetry.record(RequestRecord(
            model="qwen2.5:7b", provider="ollama", tier="SMALL",
            input_tokens=100, output_tokens=50,
            actual_cost=0.0, frontier_cost=0.001,
            local=True, intent="summarization",
        ))
        text = telemetry.format_report()
        assert "Efficient AI" in text
        assert "Data center queries avoided" in text
        assert "1" in text  # at least one request

    def test_empty_report(self, telemetry):
        text = telemetry.format_report()
        assert "No requests" in text

    def test_clear(self, telemetry):
        telemetry.record(RequestRecord(model="test", provider="test", tier="SMALL"))
        assert telemetry.total_requests() == 1
        telemetry.clear()
        assert telemetry.total_requests() == 0

    def test_savings_calculation(self, telemetry):
        """Savings = frontier_cost - actual_cost."""
        telemetry.record(RequestRecord(
            model="qwen2.5:7b", provider="ollama", tier="SMALL",
            input_tokens=1000, output_tokens=500,
            actual_cost=0.0, frontier_cost=0.0125,
            local=True, intent="simple_qa",
        ))
        report = telemetry.report()
        assert report["total_savings"] == pytest.approx(0.0125)
        assert report["savings_percentage"] == pytest.approx(100.0)
