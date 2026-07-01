"""x402-enabled OpenAI-compatible proxy server.

Wraps Efficient AI's routing pipeline (engine → Ollama → cloud) behind an
OpenAI-compatible API that charges per-request via x402 micropayments.

Pricing is dynamic based on routing:
    - Engine-handled (88% of queries): $0.0001  (basically free)
    - Local model (Ollama):            $0.001   (cheaper than any cloud)
    - Cloud fallback (GPT-4o etc):     $0.01    (pass-through + small markup)

Usage:
    # Start the server
    efficient serve --port 8000

    # Or programmatically
    from efficient.proxy import create_app
    app = create_app()
    # Run with uvicorn: uvicorn efficient.proxy:app

    # Clients pay via x402 — no API key needed
    # Using the x402 Python SDK:
    from x402 import x402Client
    from x402.mechanisms.evm.exact import ExactEvmScheme

    client = x402Client()
    client.register("eip155:8453", ExactEvmScheme(signer=my_signer))

    # The client automatically handles 402 → pay → retry
    response = httpx.post("http://localhost:8000/v1/chat/completions", json={
        "model": "auto",
        "messages": [{"role": "user", "content": "What is 2 + 2?"}],
    })
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid

# Pricing tiers (in USD per request)
PRICING = {
    "engine": 0.0001,   # Embedded deterministic engine — basically free
    "ollama": 0.001,    # Local model inference — cheaper than any cloud
    "cloud": 0.01,      # Cloud fallback — pass-through + small markup
}

# Optional Prometheus metrics (no-op fallback if not installed)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

    REQUEST_COUNT = Counter(
        'efficient_requests_total',
        'Total number of requests',
        ['tier', 'status']
    )
    REQUEST_LATENCY = Histogram(
        'efficient_request_latency_seconds',
        'Request latency in seconds',
        ['tier']
    )
    CACHE_HIT_RATE = Gauge(
        'efficient_cache_hit_rate',
        'Cache hit rate percentage'
    )
    BACKEND_DISTRIBUTION = Counter(
        'efficient_backend_requests_total',
        'Total requests per backend',
        ['backend']
    )
    PAYMENT_VERIFICATION_COUNT = Counter(
        'efficient_payment_verifications_total',
        'Total payment verifications',
        ['status']
    )
    ACTIVE_REQUESTS = Gauge(
        'efficient_active_requests',
        'Number of active requests'
    )
except ImportError:
    # No-op metrics for environments without prometheus-client
    class _NoOpMetric:
        def labels(self, **kwargs):
            return self
        def inc(self, amount=1):
            pass
        def dec(self, amount=1):
            pass
        def observe(self, value):
            pass
        def set(self, value):
            pass

    class _NoOpHistogram(_NoOpMetric):
        def time(self):
            class _Timer:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
            return _Timer()

    REQUEST_COUNT = _NoOpMetric()
    REQUEST_LATENCY = _NoOpHistogram()
    CACHE_HIT_RATE = _NoOpMetric()
    BACKEND_DISTRIBUTION = _NoOpMetric()
    PAYMENT_VERIFICATION_COUNT = _NoOpMetric()
    ACTIVE_REQUESTS = _NoOpMetric()
    generate_latest = lambda: b""
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

# Default configuration
DEFAULT_WALLET = os.environ.get("EFFICIENT_WALLET", "")
DEFAULT_NETWORK = os.environ.get("EFFICIENT_NETWORK", "eip155:8453")  # Base
DEFAULT_FACILITATOR_URL = os.environ.get(
    "EFFICIENT_FACILITATOR_URL",
    "https://x402.org/facilitator",
)

# USDC contract addresses by network
USDC_ADDRESSES = {
    "eip155:8453": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Base mainnet
    "eip155:84531": "0x833589fCD6eDb6E08f4c7C32D4f71b54bDA02913",  # Base Sepolia testnet
    "eip155:1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Ethereum mainnet
    "eip155:11155111": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",  # Sepolia testnet
}


def create_app(
    wallet_address: str = "",
    network: str = DEFAULT_NETWORK,
    facilitator_url: str = DEFAULT_FACILITATOR_URL,
    efficient_client=None,
):
    """Create a FastAPI app with x402 payment middleware.

    Args:
        wallet_address: EVM wallet address to receive payments (required for production)
        network: CAIP-2 network identifier (default: Base mainnet)
        facilitator_url: x402 facilitator URL for payment verification
        efficient_client: An Efficient AI Client instance. If None, creates one.

    """
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
        from starlette.background import BackgroundTask
        from pydantic import BaseModel
    except ImportError as err:
        raise ImportError(
            "FastAPI not installed. Install with: pip install fastapi uvicorn",
        ) from err

    if efficient_client is None:
        from efficient.client import Client
        efficient_client = Client()

    # Create a single LocalEngine instance to reuse across requests
    from efficient.local_engine import LocalEngine
    local_engine = LocalEngine()

    wallet = wallet_address or DEFAULT_WALLET
    if not wallet:
        # Allow running without payments (free mode) for development
        print("⚠ No wallet address set — running in FREE mode (no x402 payments)")
        print("  Set EFFICIENT_WALLET env var or pass wallet_address to enable payments")

    app = FastAPI(
        title="Efficient AI Proxy",
        description="OpenAI-compatible API with x402 micropayments. "
                    "88% of queries handled by embedded engine for $0.0001. "
                    "No API key needed — pay per request via x402.",
        version="0.1.0",
    )

    # Cache telemetry instance for metrics
    telemetry_instance = None
    try:
        from efficient.telemetry import Telemetry
        telemetry_instance = Telemetry()
    except Exception:
        pass

    # ── Pydantic models for OpenAI-compatible API ──

    class ChatMessage(BaseModel):
        role: str
        content: str

    class ChatCompletionRequest(BaseModel):
        model: str = "auto"
        messages: list[ChatMessage]
        temperature: float | None = 1.0
        max_tokens: int | None = None
        stream: bool | None = False
        response_format: dict | None = None

        model_config = {"extra": "allow"}

    # ── x402 payment helpers ──

    def _build_payment_requirements(price_usd: float) -> dict:
        """Build x402 payment requirements payload."""
        # Price in USDC (6 decimals)
        price_atomic = str(int(price_usd * 1_000_000))
        # Get USDC address for the configured network, default to Base mainnet
        usdc_address = USDC_ADDRESSES.get(network, USDC_ADDRESSES["eip155:8453"])
        return {
            "scheme": "exact",
            "network": network,
            "pay_to": wallet,
            "price": {
                "amount": price_atomic,
                "asset": usdc_address,
                "extra": {"name": "USDC", "version": "2"},
            },
            "description": "Efficient AI — chat completion",
            "mimeType": "application/json",
        }

    def _encode_payment_requirements(req: dict) -> str:
        """Base64-encode payment requirements for the PAYMENT-REQUIRED header."""
        return base64.b64encode(json.dumps(req).encode()).decode()

    def _decode_payment_payload(payload_b64: str) -> dict:
        """Decode the PAYMENT-SIGNATURE header."""
        try:
            decoded_bytes = base64.b64decode(payload_b64)
            decoded_str = decoded_bytes.decode()
            decoded = json.loads(decoded_str)
        except (base64.binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid payment payload: {e}") from e
        if not isinstance(decoded, dict):
            raise ValueError("Payment payload must be a JSON object")
        return decoded

    async def _verify_payment(payment_header: str, requirements: dict) -> bool:
        """Verify a payment via the x402 facilitator.

        In production, this calls the facilitator API to verify the signed
        payment payload. For development/free mode, returns True.
        """
        if not wallet:
            return True  # Free mode

        try:
            import httpx
            payload = _decode_payment_payload(payment_header)
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{facilitator_url}/verify",
                    json={
                        "paymentPayload": payload,
                        "paymentRequirements": requirements,
                    },
                    timeout=10.0,
                )
                return resp.status_code == 200
        except (httpx.TimeoutException, httpx.HTTPStatusError, json.JSONDecodeError) as e:
            # Log specific errors for debugging
            print(f"Payment verification error: {type(e).__name__}: {e!s}")
            return False
        except Exception as e:
            # Catch-all for unexpected errors
            print(f"Unexpected payment verification error: {type(e).__name__}: {e!s}")
            return False

    def _determine_price(provider: str) -> float:
        """Get the price for a given provider tier."""
        if provider in PRICING:
            return PRICING[provider]
        return PRICING["cloud"]  # Default to cloud pricing

    def _make_chat_completion(content: str, model: str, input_tokens: int, output_tokens: int):
        """Build an OpenAI-compatible chat completion response."""
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                },
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }

    # ── Routes ──

    @app.get("/")
    async def root():
        return {
            "service": "Efficient AI Proxy",
            "version": "0.1.0",
            "pricing": PRICING,
            "wallet": wallet or "(not set — free mode)",
            "network": network,
            "endpoints": {
                "chat": "/v1/chat/completions",
                "models": "/v1/models",
                "health": "/health",
                "metrics": "/metrics",
            },
        }

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    async def health():
        return {"status": "ok", "engine": "available"}

    @app.get("/v1/models")
    async def list_models():
        return {
            "object": "list",
            "data": [
                {"id": "auto", "object": "model", "owned_by": "efficient"},
                {"id": "local-engine", "object": "model", "owned_by": "efficient"},
            ],
        }

    # Add the endpoint directly to the app's router to bypass FastAPI validation
    async def chat_completions_handler(request: Request):
        """OpenAI-compatible chat completions endpoint with x402 payments.
        """
        # Parse JSON body
        import json
        try:
            body = await request.json()
        except Exception:
            try:
                body_str = await request.body()
                if not body_str:
                    return JSONResponse(
                        status_code=400,
                        content={"error": {"message": "Empty request body", "type": "invalid_request"}},
                    )
                body = json.loads(body_str.decode())
            except Exception as e2:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": f"Invalid JSON: {e2!s}", "type": "invalid_request"}},
                )

        messages = body.get("messages", [])
        model = body.get("model", "auto")
        stream = body.get("stream", False)
        response_format = body.get("response_format")

        # Validate messages list is not empty
        if not messages:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "Messages list cannot be empty", "type": "invalid_request"}},
            )

        # Validate and convert messages to dict format
        msg_dicts = []
        for m in messages:
            if not isinstance(m, dict):
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": "Each message must be a JSON object", "type": "invalid_request"}},
                )
            if "role" not in m:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": "Message missing 'role' field", "type": "invalid_request"}},
                )
            if "content" not in m:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": "Message missing 'content' field", "type": "invalid_request"}},
                )
            if not m["role"] or not isinstance(m["role"], str):
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": "Message 'role' must be a non-empty string", "type": "invalid_request"}},
                )
            if m["content"] is None or (isinstance(m["content"], str) and not m["content"].strip()):
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": "Message 'content' cannot be empty", "type": "invalid_request"}},
                )
            msg_dicts.append({"role": m["role"], "content": m["content"]})

        # Route to determine tier and price
        try:
            decision = efficient_client.router.route(msg_dicts)
            if local_engine.can_handle(decision.intent, decision.complexity):
                tier = "engine"
            elif decision.model.is_local:
                tier = "ollama"
            else:
                tier = "cloud"
        except Exception as e:
            print(f"Routing error: {type(e).__name__}: {e!s}")
            return JSONResponse(
                status_code=500,
                content={"error": {"message": "Routing failed", "type": "internal_error"}},
            )

        price = _determine_price(tier)

        # Check for payment
        payment_header = request.headers.get("PAYMENT-SIGNATURE", "")

        if not payment_header and wallet:
            requirements = _build_payment_requirements(price)
            return JSONResponse(
                status_code=402,
                content=requirements,
                headers={
                    "PAYMENT-REQUIRED": _encode_payment_requirements(requirements),
                    "X-Price": f"${price:.4f}",
                    "X-Tier": tier,
                },
            )

        # Verify payment (skip in free mode)
        if wallet and payment_header:
            requirements = _build_payment_requirements(price)
            verified = await _verify_payment(payment_header, requirements)
            PAYMENT_VERIFICATION_COUNT.labels(status="success" if verified else "failed").inc()
            if not verified:
                return JSONResponse(
                    status_code=402,
                    content={"error": "Payment verification failed"},
                    headers={
                        "PAYMENT-REQUIRED": _encode_payment_requirements(requirements),
                        "X-Price": f"${price:.4f}",
                        "X-Tier": tier,
                    },
                )

        # Process the request through Efficient AI
        start_time = time.time()
        ACTIVE_REQUESTS.inc()
        
        try:
            eff_model = "auto" if model in ("auto", "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo", "") else model
            response = efficient_client.chat(messages=msg_dicts, model=eff_model, response_format=response_format)

            # Update cache hit rate if available (using cached telemetry instance)
            if efficient_client.cache and telemetry_instance:
                try:
                    stats = telemetry_instance.get_stats()
                    if stats and "cache_hit_rate" in stats:
                        CACHE_HIT_RATE.set(stats["cache_hit_rate"] * 100)
                except Exception as e:
                    print(f"Error updating cache hit rate: {type(e).__name__}: {e!s}")

            if stream:
                # For streaming, record metrics after streaming completes
                async def stream_generator():
                    chunk = {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": response.model,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": response.content}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    final_chunk = {
                        "id": chunk["id"], "object": "chat.completion.chunk", "created": chunk["created"],
                        "model": response.model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
                
                from fastapi.responses import StreamingResponse
                
                # Record metrics after streaming completes using background task
                def record_streaming_metrics():
                    REQUEST_COUNT.labels(tier=tier, status="success").inc()
                    BACKEND_DISTRIBUTION.labels(backend=response.provider).inc()
                    REQUEST_LATENCY.labels(tier=tier).observe(time.time() - start_time)
                
                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={"X-Tier": response.provider, "X-Price": f"${price:.4f}", "X-Model": response.model},
                    background=BackgroundTask(record_streaming_metrics)
                )

            # Non-streaming: record metrics immediately
            REQUEST_COUNT.labels(tier=tier, status="success").inc()
            BACKEND_DISTRIBUTION.labels(backend=response.provider).inc()
            REQUEST_LATENCY.labels(tier=tier).observe(time.time() - start_time)
            
            result = _make_chat_completion(content=response.content, model=response.model, input_tokens=response.input_tokens, output_tokens=response.output_tokens)
            return JSONResponse(content=result, headers={"X-Tier": response.provider, "X-Price": f"${price:.4f}", "X-Model": response.model, "X-Latency-ms": f"{response.latency_ms:.1f}"})
        except Exception as e:
            REQUEST_COUNT.labels(tier=tier, status="error").inc()
            return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": "internal_error"}})
        finally:
            ACTIVE_REQUESTS.dec()

    # Register the route manually
    app.add_route("/v1/chat/completions", chat_completions_handler, methods=["POST"])

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    wallet_address: str = "",
    network: str = DEFAULT_NETWORK,
):
    """Run the x402 proxy server."""
    try:
        import uvicorn
    except ImportError as err:
        raise ImportError(
            "uvicorn not installed. Install with: pip install uvicorn",
        ) from err

    app = create_app(
        wallet_address=wallet_address,
        network=network,
    )
    print("\nEfficient AI — x402 Proxy Server")
    print(f"  Listening:  http://{host}:{port}")
    print(f"  Endpoint:   http://{host}:{port}/v1/chat/completions")
    print(f"  Network:    {network}")
    print(f"  Wallet:     {wallet_address or '(free mode)'}")
    print(f"  Pricing:    engine=${PRICING['engine']:.4f} | "
          f"ollama=${PRICING['ollama']:.4f} | "
          f"cloud=${PRICING['cloud']:.4f}")
    print()

    uvicorn.run(app, host=host, port=port)
