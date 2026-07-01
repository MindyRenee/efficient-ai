"""
Performance benchmarks for Efficient AI.

Run with: python -m pytest benchmarks/benchmark.py --benchmark-only
Requires: pip install pytest-benchmark
"""

import pytest

from efficient.cache import SemanticCache
from efficient.client import Client
from efficient.local_engine import LocalEngine
from efficient.router import Router


class TestBenchmarks:
    """Performance benchmarks for core components."""

    @pytest.fixture
    def engine(self):
        """LocalEngine instance."""
        return LocalEngine()

    @pytest.fixture
    def router(self):
        """Router instance."""
        return Router()

    @pytest.fixture
    def cache(self):
        """SemanticCache instance."""
        return SemanticCache()

    @pytest.fixture
    def client(self):
        """Client instance."""
        return Client()

    def test_engine_simple_qa_latency(self, engine, benchmark):
        """Benchmark simple Q&A latency."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]

        def run():
            return engine.handle(messages)

        result = benchmark(run)
        assert result.handled
        # Should be < 1ms for simple queries

    def test_engine_summarization_latency(self, engine, benchmark):
        """Benchmark summarization latency."""
        text = "The quick brown fox jumps over the lazy dog. " * 10

        def run():
            return engine.summarize(text)

        result = benchmark(run)
        assert result.handled

    def test_engine_classification_latency(self, engine, benchmark):
        """Benchmark classification latency."""
        text = "I love this product! It's amazing."

        def run():
            return engine.classify(text, "sentiment")

        result = benchmark(run)
        assert result.handled

    def test_router_classification_latency(self, router, benchmark):
        """Benchmark intent classification latency."""
        messages = [{"role": "user", "content": "What is the capital of France?"}]

        def run():
            return router.route(messages)

        result = benchmark(run)
        assert result.intent == "simple_qa"

    def test_cache_lookup_latency(self, cache, benchmark):
        """Benchmark cache lookup latency."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]

        def run():
            return cache.get(messages)

        benchmark(run)

    def test_cache_store_latency(self, cache, benchmark):
        """Benchmark cache store latency."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]
        response = "2 + 2 = 4"

        def run():
            return cache.set(messages, response)

        benchmark(run)

    def test_client_chat_latency(self, client, benchmark):
        """Benchmark client chat latency (engine only)."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]

        def run():
            return client.chat(messages=messages)

        result = benchmark(run)
        assert result.provider == "engine"

    def test_engine_throughput(self, engine, benchmark):
        """Benchmark engine throughput (requests per second)."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]

        def run():
            for _ in range(100):
                engine.handle(messages)

        benchmark.pedantic(run, iterations=10, rounds=5)

    def test_cache_hit_rate(self, cache):
        """Benchmark cache hit rate with repeated queries."""
        messages = [{"role": "user", "content": "What is 2 + 2?"}]
        response = "2 + 2 = 4"

        # Store once
        cache.set(messages, response)

        # Retrieve 100 times
        hits = 0
        for _ in range(100):
            if cache.get(messages):
                hits += 1

        # Should have 100% hit rate
        assert hits == 100

    def test_memory_usage(self, engine):
        """Test memory usage for large inputs."""
        import tracemalloc

        tracemalloc.start()

        # Process large text
        large_text = "The quick brown fox " * 10000
        engine.summarize(large_text)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be reasonable (< 100MB for this operation)
        assert peak < 100 * 1024 * 1024


if __name__ == "__main__":
    pytest.main([__file__, "--benchmark-only", "--benchmark-columns=min,max,mean,stddev"])
