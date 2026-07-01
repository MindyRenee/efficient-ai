"""
Tests for the main Client — integration tests for the orchestration layer.

These tests use mock backends to avoid requiring Ollama or cloud API keys.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from efficient.backends import Backend, GenerateResponse
from efficient.client import ChatResponse, Client
from efficient.config import CloudKeys, Config, GPUInfo, OllamaInfo
from efficient.models import ModelInfo


class MockBackend(Backend):
    """Mock backend for testing."""

    def __init__(self, provider: str = "ollama", available: bool = True):
        self._provider = provider
        self._available = available
        self.calls: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return self._available

    def chat(
        self,
        model: ModelInfo,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> GenerateResponse:
        self.calls.append({"model": model.name, "messages": messages})
        return GenerateResponse(
            content=f"Mock response from {model.name}",
            model=model.name,
            provider=self._provider,
            input_tokens=50,
            output_tokens=30,
            latency_ms=10.0,
        )

    def stream_chat(self, model, messages, **kwargs):
        yield "Mock "
        yield "stream "
        yield f"from {model.name}"


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    """Create a config with mocked paths and no real backends."""
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    config = Config(
        gpu=GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24576),
        ollama=OllamaInfo(
            installed=True,
            running=True,
            host="http://localhost:11434",
            models=["qwen2.5:7b", "qwen2.5:14b", "phi3:mini"],
        ),
        cloud=CloudKeys(openai="test-key"),
        preferred_local_model="qwen2.5:7b",
        cache_db_path=str(tmp_path / "cache.db"),
        telemetry_db_path=str(tmp_path / "telemetry.db"),
    )
    return config


@pytest.fixture
def client(mock_config):
    """Create a client with mock backends."""
    client = Client.__new__(Client)
    client.config = mock_config

    # Init cache
    from efficient.cache import SemanticCache

    client.cache = SemanticCache(
        db_path=mock_config.cache_db_path,
        ollama_host="http://localhost:99999",  # Force hash embeddings
    )

    # Init mock backends — engine is real, ollama/openai are mocked
    from efficient.backends import LocalEngineBackend

    client.backends = {
        "engine": LocalEngineBackend(),
        "ollama": MockBackend("ollama"),
        "openai": MockBackend("openai"),
    }

    # Init router
    from efficient.router import Router

    client.router = Router(
        vram_gb=24,
        available_local_models=["qwen2.5:7b", "qwen2.5:14b", "phi3:mini"],
        available_providers=["openai"],
        local_first=True,
        preferred_local="qwen2.5:7b",
        preferred_cloud="gpt-4o-mini",
        fallback_cloud="gpt-4o",
    )

    # Init telemetry
    from efficient.telemetry import Telemetry

    client.telemetry = Telemetry(db_path=mock_config.telemetry_db_path)

    # Init chat interface
    from efficient.client import ChatInterface

    client.chat = ChatInterface(client)

    return client


class TestClient:
    def test_chat_returns_response(self, client):
        response = client.chat(messages=[{"role": "user", "content": "Hello"}])
        assert isinstance(response, ChatResponse)
        assert response.content
        assert response.model
        assert response.provider

    def test_chat_routes_to_engine(self, client):
        response = client.chat(messages=[{"role": "user", "content": "What is 2 + 2?"}])
        assert response.local
        assert response.provider == "engine"

    def test_chat_cache_hit(self, client):
        """Second identical request should hit cache."""
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        r1 = client.chat(messages=msgs)
        assert not r1.cache_hit

        r2 = client.chat(messages=msgs)
        assert r2.cache_hit
        assert r2.content == r1.content

    def test_chat_telemetry_recorded(self, client):
        client.chat(messages=[{"role": "user", "content": "Hello"}])
        assert client.telemetry.total_requests() == 1

    def test_chat_savings_tracked(self, client):
        """Local inference should show savings vs frontier cost."""
        response = client.chat(messages=[{"role": "user", "content": "Summarize this text"}])
        assert response.cost == 0.0  # Local is free
        assert response.frontier_cost > 0  # Would have cost on GPT-5
        assert response.savings > 0

    def test_openai_compatible_interface(self, client):
        """The OpenAI-compatible interface should return a dict."""
        result = client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert isinstance(result, dict)
        assert "choices" in result
        assert "usage" in result
        assert "_efficient" in result
        assert result["choices"][0]["message"]["content"]

    def test_streaming(self, client):
        chunks = list(
            client.chat_stream(
                messages=[{"role": "user", "content": "Hello"}],
            )
        )
        assert len(chunks) > 0
        assert "".join(chunks)

    def test_status_output(self, client):
        status = client.status()
        assert "Efficient AI" in status
        assert "engine" in status or "ollama" in status

    def test_report_output(self, client):
        client.chat(messages=[{"role": "user", "content": "Hello"}])
        report = client.report()
        assert "Efficient AI" in report
        assert "Data center queries avoided" in report

    def test_cloud_fallback_on_engine_failure(self, client):
        """If engine can't handle and ollama fails, should fall back to cloud."""
        # Make ollama backend raise an error
        client.backends["ollama"].chat = MagicMock(side_effect=Exception("Ollama crashed"))

        # This request is too complex for the engine, so it'll try ollama, then cloud
        response = client.chat(
            messages=[
                {
                    "role": "user",
                    "content": "Plan and execute a complex multi-step agentic workflow with tool calls and reasoning",
                }
            ]
        )
        # Should have fallen back to cloud
        assert response.provider == "openai"

    def test_routing_for_different_intents(self, client):
        """Different intents should route to different backends."""
        # Simple classification → should use engine (local, free)
        r1 = client.chat(messages=[{"role": "user", "content": "Classify sentiment: I love this"}])
        assert r1.local

        # Complex reasoning → engine can't handle, should escalate
        r2 = client.chat(
            messages=[{"role": "user", "content": "Why is the sky blue? Explain step by step."}]
        )
        assert r2.routing is not None
        assert r2.routing.intent == "reasoning"
