"""
Tests for the x402-enabled proxy server.

Tests use FastAPI's TestClient which doesn't require a running server.
The proxy is tested in free mode (no wallet) so no actual payments are needed.
"""

import pytest

# Skip all tests if fastapi not installed
fastapi = pytest.importorskip("fastapi")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture
def client():
    """Create a test client for the proxy app in free mode (no wallet)."""
    from efficient.proxy import create_app
    app = create_app(wallet_address="")
    return TestClient(app)


class TestProxyRoot:
    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Efficient AI Proxy"
        assert "pricing" in data
        assert data["pricing"]["engine"] == 0.0001

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_models_endpoint(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        ids = [m["id"] for m in data["data"]]
        assert "auto" in ids
        assert "local-engine" in ids


class TestProxyChat:
    def test_chat_completion_engine(self, client):
        """Engine-handled query (arithmetic) should return a valid response."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "4" in data["choices"][0]["message"]["content"]
        assert "usage" in data
        # Engine may return 0 tokens (deterministic, not LLM)
        assert data["usage"]["total_tokens"] >= 0

    def test_chat_completion_headers(self, client):
        """Response should include tier and pricing headers."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 200
        assert "x-tier" in resp.headers
        assert "x-price" in resp.headers
        assert "x-model" in resp.headers

    def test_chat_completion_summarization(self, client):
        """Summarization should be handled by engine."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Summarize: The weather today is sunny with a high of 75 degrees and light winds from the west. Tomorrow will bring rain showers in the afternoon."}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["choices"][0]["message"]["content"]) > 0

    def test_chat_completion_code_gen(self, client):
        """Code generation should be handled by engine."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Write a Python function that returns the factorial of n."}],
        })
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "def factorial" in content

    def test_chat_completion_knowledge_qa(self, client):
        """Knowledge Q&A should be handled by engine."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is the capital of France?"}],
        })
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "Paris" in content

    def test_chat_completion_algebra(self, client):
        """Algebra solver should work through the proxy."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "Solve 2x + 3 = 7"}],
        })
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        assert "x = 2" in content

    def test_streaming_response(self, client):
        """Streaming should return SSE format."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
            "stream": True,
        })
        assert resp.status_code == 200
        text = resp.text
        assert "data: " in text
        assert "[DONE]" in text

    def test_empty_messages(self, client):
        """Empty messages should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [],
        })
        assert resp.status_code == 400

    def test_different_model_names(self, client):
        """Various model names should all work (mapped to auto)."""
        for model in ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"]:
            resp = client.post("/v1/chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": "What is 2 + 2?"}],
            })
            assert resp.status_code == 200
            assert "4" in resp.json()["choices"][0]["message"]["content"]


class TestProxyPricing:
    def test_engine_tier_pricing(self, client):
        """Engine-handled query should show engine pricing in headers."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 200
        tier = resp.headers.get("x-tier", "")
        price = resp.headers.get("x-price", "")
        # Tier can be engine, ollama, cloud, or cache
        assert tier in ("engine", "ollama", "cloud", "cache")
        assert "$" in price

    def test_pricing_values(self, client):
        """Pricing should match the defined tiers."""
        from efficient.proxy import PRICING
        assert PRICING["engine"] == 0.0001
        assert PRICING["ollama"] == 0.001
        assert PRICING["cloud"] == 0.01


class TestProxyPaymentFlow:
    def test_402_returned_with_wallet(self):
        """When wallet is set and no payment header, should return 402."""
        from efficient.proxy import create_app
        app = create_app(wallet_address="0x1234567890123456789012345678901234567890")
        test_client = TestClient(app)

        resp = test_client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 402
        assert "payment-required" in {k.lower() for k in resp.headers}
        assert "x-price" in resp.headers
        assert "x-tier" in resp.headers

    def test_free_mode_no_402(self, client):
        """In free mode (no wallet), should never return 402."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 200


class TestProxyErrorHandling:
    def test_malformed_json(self, client):
        """Malformed JSON should return 400 error."""
        resp = client.post(
            "/v1/chat/completions",
            content=b'{"model": "auto", "messages": [{"role": "user", "content": "What is 2 + 2?"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_empty_request_body(self, client):
        """Empty request body should return 400 error."""
        resp = client.post(
            "/v1/chat/completions",
            content=b'',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_empty_messages_list(self, client):
        """Empty messages list should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [],
        })
        assert resp.status_code == 400
        assert "empty" in resp.json()["error"]["message"].lower()

    def test_message_missing_role(self, client):
        """Message missing 'role' field should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 400
        assert "role" in resp.json()["error"]["message"].lower()

    def test_message_missing_content(self, client):
        """Message missing 'content' field should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user"}],
        })
        assert resp.status_code == 400
        assert "content" in resp.json()["error"]["message"].lower()

    def test_message_empty_role(self, client):
        """Message with empty role should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "", "content": "What is 2 + 2?"}],
        })
        assert resp.status_code == 400
        assert "role" in resp.json()["error"]["message"].lower()

    def test_message_empty_content(self, client):
        """Message with empty content should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": ""}],
        })
        assert resp.status_code == 400
        assert "content" in resp.json()["error"]["message"].lower()

    def test_message_not_dict(self, client):
        """Message that is not a dict should return 400 error."""
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": ["invalid message"],
        })
        assert resp.status_code == 400
        assert "json object" in resp.json()["error"]["message"].lower()
