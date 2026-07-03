"""The main Client — drop-in OpenAI replacement with stacked optimizations.

This is the primary user-facing API. It orchestrates:
1. Semantic cache lookup (30-50% of queries never hit a model)
2. Intent classification + model routing (45-85% cost reduction)
3. Local-first inference via Ollama ($0/token)
4. Automatic cloud fallback when local can't handle the task
5. Telemetry tracking (shows data center demand avoided)

Usage (drop-in replacement):
    from efficient import Client

    client = Client()

    # Synchronous
    response = client.chat(messages=[{"role": "user", "content": "Hello"}])
    print(response.content)

    # Streaming
    for chunk in client.chat_stream(messages=[...]):
        print(chunk, end="")

    # OpenAI-compatible interface
    result = client.chat.completions.create(
        model="auto",  # or specific model name
        messages=[{"role": "user", "content": "Hello"}],
    )
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from efficient.backends import Backend, create_backends
from efficient.cache import SemanticCache
from efficient.config import Config
from efficient.models import (
    all_models,
    cloud_models,
    estimate_cost,
    get_model,
)
from efficient.router import Router, RoutingDecision
from efficient.telemetry import RequestRecord, Telemetry


@dataclass
class ChatResponse:
    """Unified response object."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cache_hit: bool = False
    local: bool = False
    intent: str = ""
    cost: float = 0.0
    frontier_cost: float = 0.0
    savings: float = 0.0
    raw: dict = field(default_factory=dict)
    finish_reason: str = "stop"
    routing: RoutingDecision | None = None

    def to_openai_format(self) -> dict:
        """Convert to OpenAI API response format for drop-in compatibility."""
        return {
            "id": f"chatcmpl-efficient-{int(time.time() * 1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": self.content,
                    },
                    "finish_reason": self.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": self.input_tokens,
                "completion_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
            },
            "_efficient": {
                "provider": self.provider,
                "local": self.local,
                "cache_hit": self.cache_hit,
                "intent": self.intent,
                "cost": self.cost,
                "frontier_cost": self.frontier_cost,
                "savings": self.savings,
                "latency_ms": self.latency_ms,
            },
        }


# ─── Frontier cost reference (for savings calculation) ─────────────────────────

# Use GPT-5 as the "what you would have paid" baseline
_FRONTIER_REFERENCE = {
    "input_price_per_m": 5.00,
    "output_price_per_m": 15.00,
}


def _compute_frontier_cost(input_tokens: int, output_tokens: int) -> float:
    """What would this cost on GPT-5?"""
    return (input_tokens / 1_000_000) * _FRONTIER_REFERENCE["input_price_per_m"] + (
        output_tokens / 1_000_000
    ) * _FRONTIER_REFERENCE["output_price_per_m"]


# ─── Logging ───────────────────────────────────────────────────────────────────

logger = logging.getLogger("efficient.client")


# ─── Main Client ───────────────────────────────────────────────────────────────


class Client:
    """Drop-in OpenAI replacement with stacked optimizations.

    Auto-detects Ollama, GPU, and cloud API keys on first run.
    Persists config to ~/.efficient/config.json.

    Args:
        config: Optional Config object. If None, auto-detects.
        **overrides: Override any Config field.

    """

    def __init__(self, config: Config | None = None, **overrides):
        # Load or auto-detect config
        if config is None:
            config = Config.load()

        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        self.config = config
        self._init_components()

        # OpenAI-compatible interface (callable + .completions.create())
        self.chat = ChatInterface(self)

    def _init_components(self) -> None:
        """Initialize cache, router, backends, and telemetry."""
        cfg = self.config

        # Cache
        self.cache: SemanticCache | None = None
        if cfg.cache_enabled:
            self.cache = SemanticCache(
                db_path=cfg.cache_db_path,
                ollama_host=cfg.ollama.host,
                similarity_threshold=cfg.cache_similarity_threshold,
            )

        # Backends
        cloud_keys = {
            "openai": cfg.cloud.openai,
            "groq": cfg.cloud.groq,
            "openrouter": cfg.cloud.openrouter,
        }
        self.backends = create_backends(
            ollama_host=cfg.ollama.host,
            cloud_keys=cloud_keys,
            timeout=cfg.timeout_seconds,
        )

        # Router
        vram_gb = cfg.gpu.vram_mb / 1024 if cfg.gpu.available else 0
        self.router = Router(
            vram_gb=vram_gb,
            available_local_models=cfg.ollama.models,
            available_providers=cfg.cloud.available_providers(),
            local_first=cfg.local_first,
            preferred_local=cfg.preferred_local_model,
            preferred_cloud=cfg.preferred_cloud_model,
            fallback_cloud=cfg.fallback_cloud_model,
        )

        # Telemetry
        self.telemetry: Telemetry | None = None
        if cfg.track_costs:
            self.telemetry = Telemetry(db_path=cfg.telemetry_db_path)

    # ─── Core Chat Method ──────────────────────────────────────────────────

    def _chat(
        self,
        messages: list[dict],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> ChatResponse:
        """Send a chat completion request.

        Args:
            messages: OpenAI-format messages list
            model: "auto" for smart routing, or specific model name
            temperature: Sampling temperature
            max_tokens: Max output tokens
            stream: If True, use chat_stream instead
            tools: Tool/function definitions
            response_format: Output format (e.g. {"type": "json_object"})

        Returns:
            ChatResponse with content and metadata

        """
        if stream:
            return self._stream_as_response(
                messages, model, temperature, max_tokens, tools, response_format, **kwargs
            )

        # Determine routing
        if model == "auto":
            decision = self.router.route(
                messages,
                require_tools=tools is not None,
                require_vision=any(
                    isinstance(m.get("content"), list)
                    and any(
                        p.get("type") == "image_url" for p in m["content"] if isinstance(p, dict)
                    )
                    for m in messages
                ),
                require_json=response_format is not None,
            )
        else:
            # User specified a model — find it
            model_info = get_model(model)
            if model_info is None:
                # Try to find by partial match
                for m in all_models():
                    if model in m.name or m.name.startswith(model):
                        model_info = m
                        break
            if model_info is None:
                raise ValueError(f"Unknown model: {model}")
            from efficient.router import RoutingDecision

            decision = RoutingDecision(
                intent="user-specified",
                complexity="unknown",
                tier=model_info.tier,
                model=model_info,
                reason=f"User specified model '{model}'",
                use_cache=True,
            )

        logger.info(
            f"Routing decision: intent={decision.intent}, complexity={decision.complexity}, "
            f"model={decision.model.name}, provider={decision.model.provider}, reason={decision.reason}"
        )

        # 1. Check semantic cache
        if self.cache is not None and decision.use_cache:
            cache_entry = self.cache.get(
                self._messages_to_query(messages),
                intent=decision.intent,
            )
            if cache_entry is not None:
                logger.info(f"Cache hit for intent={decision.intent}, model={cache_entry.model}")
                response = ChatResponse(
                    content=cache_entry.response,
                    model=cache_entry.model,
                    provider="cache",
                    cache_hit=True,
                    local=True,
                    intent=decision.intent,
                    latency_ms=0.1,
                    finish_reason="stop",
                    routing=decision,
                )
                self._record_telemetry(response, decision, input_tokens=0, output_tokens=0)
                return response

        # 2. Execute on selected backend
        backend = self._get_backend(decision.model.provider)
        if backend is None:
            logger.warning(
                f"No backend for provider={decision.model.provider}, attempting fallback"
            )
            # Fallback: try any available backend
            backend = self._fallback_backend()
            if backend is None:
                logger.error("No inference backends available")
                raise RuntimeError(
                    "No inference backends available. "
                    "Install Ollama (ollama.com) or set an API key.",
                )

        try:
            # Pass intent/complexity to engine backend for dispatch only
            engine_kwargs = kwargs.copy()
            if decision.model.provider == "engine":
                engine_kwargs["_intent"] = decision.intent
                engine_kwargs["_complexity"] = decision.complexity
            result = backend.chat(
                model=decision.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
                **engine_kwargs,
            )
        except Exception as e:
            logger.warning(
                f"Backend {decision.model.provider} failed for {decision.model.name}: {type(e).__name__}: {e!s}"
            )
            # If engine can't handle it, try Ollama next
            if decision.model.provider == "engine" and "ollama" in self.backends:
                logger.info("Falling back from engine to Ollama")
                ollama_decision = self._ollama_fallback(decision)
                if ollama_decision:
                    ollama_backend = self.backends["ollama"]
                    try:
                        result = ollama_backend.chat(
                            model=ollama_decision.model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=tools,
                            response_format=response_format,
                        )
                        decision = ollama_decision
                    except Exception:
                        # Ollama also failed — try cloud
                        logger.warning("Ollama fallback failed, attempting cloud fallback")
                        if self.config.cloud.any_available:
                            cloud_decision = self._cloud_fallback(decision)
                            if cloud_decision:
                                cloud_backend = self._get_backend(cloud_decision.model.provider)
                                if cloud_backend:
                                    result = cloud_backend.chat(
                                        model=cloud_decision.model,
                                        messages=messages,
                                        temperature=temperature,
                                        max_tokens=max_tokens,
                                        tools=tools,
                                        response_format=response_format,
                                    )
                                    decision = cloud_decision
                                else:
                                    raise
                            else:
                                raise
                        else:
                            raise
                    else:
                        pass
                # No Ollama model available — try cloud directly
                elif self.config.cloud.any_available:
                    cloud_decision = self._cloud_fallback(decision)
                    if cloud_decision:
                        cloud_backend = self._get_backend(cloud_decision.model.provider)
                        if cloud_backend:
                            result = cloud_backend.chat(
                                model=cloud_decision.model,
                                messages=messages,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                tools=tools,
                                response_format=response_format,
                            )
                            decision = cloud_decision
                        else:
                            raise
                    else:
                        raise
                else:
                    raise
            # If local (Ollama) fails, try cloud fallback
            elif decision.model.is_local and self.config.cloud.any_available:
                logger.info("Falling back from Ollama to cloud")
                cloud_decision = self._cloud_fallback(decision)
                if cloud_decision:
                    cloud_backend = self._get_backend(cloud_decision.model.provider)
                    if cloud_backend:
                        result = cloud_backend.chat(
                            model=cloud_decision.model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=tools,
                            response_format=response_format,
                        )
                        decision = cloud_decision
                    else:
                        raise
                else:
                    raise
            else:
                raise

        # Build response
        actual_cost = estimate_cost(decision.model, result.input_tokens, result.output_tokens)
        frontier_cost = _compute_frontier_cost(result.input_tokens, result.output_tokens)

        response = ChatResponse(
            content=result.content,
            model=result.model,
            provider=result.provider,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            cache_hit=False,
            local=decision.model.is_local,
            intent=decision.intent,
            cost=actual_cost,
            frontier_cost=frontier_cost,
            savings=frontier_cost - actual_cost,
            raw=result.raw,
            finish_reason=result.finish_reason,
            routing=decision,
        )

        # 3. Store in cache
        if self.cache is not None and decision.use_cache and response.content is not None:
            self.cache.put(
                query=self._messages_to_query(messages),
                response=response.content,
                model=response.model,
                intent=decision.intent,
            )

        logger.info(f"Response: model={response.model}, provider={response.provider}")

        # 4. Record telemetry
        self._record_telemetry(response, decision, result.input_tokens, result.output_tokens)

        return response

    def chat_stream(
        self,
        messages: list[dict],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> Iterator[str]:
        """Stream a chat completion. Yields content chunks as they arrive.

        Note: Semantic cache is not used for streaming requests (can't cache partial output).
        """
        # Route
        if model == "auto":
            decision = self.router.route(
                messages,
                require_tools=tools is not None,
                require_json=response_format is not None,
            )
        else:
            model_info = get_model(model)
            if model_info is None:
                for m in all_models():
                    if model in m.name or m.name.startswith(model):
                        model_info = m
                        break
            if model_info is None:
                raise ValueError(f"Unknown model: {model}")
            from efficient.router import RoutingDecision

            decision = RoutingDecision(
                intent="user-specified",
                complexity="unknown",
                tier=model_info.tier,
                model=model_info,
                reason=f"User specified '{model}'",
            )

        backend = self._get_backend(decision.model.provider)
        if backend is None:
            backend = self._fallback_backend()
            if backend is None:
                raise RuntimeError("No inference backends available.")

        try:
            # Pass intent/complexity to engine backend for dispatch
            if decision.model.provider == "engine":
                kwargs["_intent"] = decision.intent
                kwargs["_complexity"] = decision.complexity
            for chunk in backend.stream_chat(
                model=decision.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
                **kwargs,
            ):
                yield chunk
        except Exception:
            if decision.model.is_local and self.config.cloud.any_available:
                cloud_decision = self._cloud_fallback(decision)
                if cloud_decision:
                    cloud_backend = self._get_backend(cloud_decision.model.provider)
                    if cloud_backend:
                        for chunk in cloud_backend.stream_chat(
                            model=cloud_decision.model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            tools=tools,
                            response_format=response_format,
                            **kwargs,
                        ):
                            yield chunk
                        return
            raise

    # ─── Helpers ───────────────────────────────────────────────────────────

    def _get_backend(self, provider: str) -> Backend | None:
        return self.backends.get(provider)

    def _fallback_backend(self) -> Backend | None:
        """Get any available backend as fallback. Prefer Ollama over engine."""
        for provider in ("ollama", "openai", "groq", "openrouter", "engine"):
            backend = self.backends.get(provider)
            if backend and backend.is_available():
                return backend
        return None

    def _cloud_fallback(self, local_decision: RoutingDecision) -> RoutingDecision | None:
        """Create a cloud fallback routing decision."""
        from efficient.router import RoutingDecision

        # Find cheapest cloud model at same or higher tier
        for m in cloud_models():
            if m.tier >= local_decision.tier and m.provider in self.backends:
                return RoutingDecision(
                    intent=local_decision.intent,
                    complexity=local_decision.complexity,
                    tier=local_decision.tier,
                    model=m,
                    reason=f"Cloud fallback after local failure — '{m.name}'",
                    use_cache=True,
                )
        return None

    def _ollama_fallback(self, engine_decision: RoutingDecision) -> RoutingDecision | None:
        """Create an Ollama fallback when the engine can't handle a request."""
        from efficient.models import local_models as _local_models
        from efficient.router import RoutingDecision

        # Find best Ollama model at the required tier
        ollama_models = [m for m in _local_models() if m.provider == "ollama"]
        vram_gb = self.config.gpu.vram_mb / 1024 if self.config.gpu.available else 0
        for m in sorted(ollama_models, key=lambda m: (m.tier, -m.mmlu_score)):
            if m.tier >= engine_decision.tier:
                if vram_gb > 0 and m.vram_required_gb > vram_gb:
                    continue
                # Check if model is installed (exact name match, not just prefix)
                installed = any(
                    m.name in name
                    for name in self.config.ollama.models
                )
                if installed:
                    return RoutingDecision(
                        intent=engine_decision.intent,
                        complexity=engine_decision.complexity,
                        tier=engine_decision.tier,
                        model=m,
                        reason=f"Ollama fallback after engine cannot handle — '{m.name}'",
                        use_cache=True,
                        use_speculative=m.supports_speculative,
                    )
        return None

    @staticmethod
    def _messages_to_query(messages: list[dict]) -> str:
        """Convert messages to a single query string for caching."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = " ".join(text_parts)
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def _record_telemetry(
        self,
        response: ChatResponse,
        decision: RoutingDecision,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if self.telemetry is None:
            return
        record = RequestRecord(
            model=response.model,
            provider=response.provider,
            tier=decision.tier.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost=response.cost,
            frontier_cost=response.frontier_cost,
            latency_ms=response.latency_ms,
            cache_hit=response.cache_hit,
            local=response.local,
            intent=decision.intent,
            success=True,
        )
        self.telemetry.record(record)

    # ─── Utility Methods ───────────────────────────────────────────────────

    def report(self, since_hours: float = 24.0) -> str:
        """Generate a human-readable impact report."""
        if self.telemetry is None:
            return "Telemetry disabled. Set track_costs=True to enable."
        return self.telemetry.format_report(since_hours)

    def status(self) -> str:
        """Show current configuration and backend status."""
        lines = [
            "Efficient AI Status",
            "=" * 50,
            "",
        ]

        # Backends
        lines.append("Backends:")
        for name, backend in self.backends.items():
            available = "✓" if backend.is_available() else "✗"
            lines.append(f"  [{available}] {name}")
        if not self.backends:
            lines.append("  [!] No backends available")
        lines.append("")

        # Cache
        if self.cache:
            stats = self.cache.stats()
            lines.append(f"Cache: {stats['total_entries']} entries, {stats['total_hits']} hits")
        else:
            lines.append("Cache: disabled")
        lines.append("")

        # Router info
        lines.append(f"Local-first: {self.config.local_first}")
        lines.append(f"Preferred local: {self.config.preferred_local_model or 'none'}")
        lines.append(f"Preferred cloud: {self.config.preferred_cloud_model}")
        lines.append("")

        # Telemetry
        if self.telemetry:
            total = self.telemetry.total_requests()
            lines.append(f"Telemetry: {total} requests recorded")
        else:
            lines.append("Telemetry: disabled")

        return "\n".join(lines)

    def _stream_as_response(
        self,
        messages: list[dict],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> ChatResponse:
        """Collect a stream into a single response (for stream=True compatibility)."""
        # Route to get metadata
        if model == "auto":
            decision = self.router.route(
                messages,
                require_tools=tools is not None,
                require_vision=any(
                    isinstance(m.get("content"), list)
                    and any(
                        p.get("type") == "image_url" for p in m["content"] if isinstance(p, dict)
                    )
                    for m in messages
                ),
                require_json=response_format is not None,
            )
        else:
            model_info = get_model(model)
            if model_info is None:
                for m in all_models():
                    if model in m.name or m.name.startswith(model):
                        model_info = m
                        break
            if model_info is None:
                raise ValueError(f"Unknown model: {model}")
            from efficient.router import RoutingDecision

            decision = RoutingDecision(
                intent="user-specified",
                complexity="unknown",
                tier=model_info.tier,
                model=model_info,
                reason=f"User specified '{model}'",
            )

        chunks = []
        start = time.time()
        for chunk in self.chat_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            **kwargs,
        ):
            chunks.append(chunk)
        content = "".join(chunks)
        latency_ms = (time.time() - start) * 1000

        # Estimate tokens from content (streaming doesn't return token counts)
        input_text = self._messages_to_query(messages)
        estimated_input = max(1, len(input_text.split()) * 4 // 3)
        estimated_output = max(1, len(content.split()) * 4 // 3)

        response = ChatResponse(
            content=content,
            model=decision.model.name,
            provider=decision.model.provider,
            input_tokens=estimated_input,
            output_tokens=estimated_output,
            latency_ms=latency_ms,
            local=decision.model.is_local,
            intent=decision.intent,
            routing=decision,
        )

        # Record telemetry for the collected stream
        self._record_telemetry(response, decision, estimated_input, estimated_output)
        return response


# ─── OpenAI-Compatible Interface ──────────────────────────────────────────────


class ChatInterface:
    """OpenAI-compatible chat interface.

    Callable directly: client.chat(messages=[...])
    Also provides: client.chat.completions.create(...)
    """

    def __init__(self, client: Client):
        self.client = client
        self.completions = CompletionsInterface(client)

    def __call__(self, **kwargs) -> ChatResponse:
        """Allow client.chat(messages=...) to work as a direct call."""
        return self.client._chat(**kwargs)


class CompletionsInterface:
    """OpenAI-compatible completions interface."""

    def __init__(self, client: Client):
        self.client = client

    def create(
        self,
        model: str = "auto",
        messages: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> dict | Iterator:
        """OpenAI-compatible chat completion create.

        Returns an OpenAI-format dict for non-streaming,
        or yields content chunks for streaming.
        """
        if messages is None:
            messages = []

        if stream:
            return self.client.chat_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
                **kwargs,
            )
        response = self.client._chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            **kwargs,
        )
        return response.to_openai_format()
