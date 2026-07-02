"""Backend abstraction layer.

Provides a unified interface for:
- Local inference via Ollama
- Cloud inference via OpenAI-compatible APIs (OpenAI, Groq, OpenRouter, Together)

All backends implement the same interface, so the client can swap
between them transparently.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from efficient.local_engine import LocalEngine
from efficient.models import ModelInfo


@dataclass
class GenerateResponse:
    """Unified response from any backend."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)
    finish_reason: str = "stop"


class Backend:
    """Base class for inference backends."""

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
        raise NotImplementedError

    def stream_chat(
        self,
        model: ModelInfo,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> Iterator[str]:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.__class__.__name__


# ─── Ollama Backend (Local) ───────────────────────────────────────────────────


class OllamaBackend(Backend):
    """Local inference via Ollama.

    Zero cost per token. Runs on your hardware.
    Supports streaming, JSON output, and tool calling.
    """

    def __init__(self, host: str = "http://localhost:11434", timeout: float = 120.0):
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def is_available(self) -> bool:
        try:
            resp = self._http.get(f"{self.host}/api/version", timeout=5.0)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

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
        start = time.time()

        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if response_format and response_format.get("type") == "json":
            payload["format"] = "json"

        if tools:
            payload["tools"] = tools

        # Speculative decoding hint (Ollama handles this if a draft model is configured)
        if model.supports_speculative and model.draft_model:
            payload["options"]["draft_model"] = model.draft_model

        payload.update(kwargs)

        resp = self._http.post(f"{self.host}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        latency = (time.time() - start) * 1000

        return GenerateResponse(
            content=data.get("message", {}).get("content", ""),
            model=model.name,
            provider="ollama",
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            latency_ms=latency,
            raw=data,
            finish_reason="stop" if data.get("done") else "length",
        )

    def stream_chat(
        self,
        model: ModelInfo,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> Iterator[str]:
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if response_format and response_format.get("type") == "json":
            payload["format"] = "json"

        if tools:
            payload["tools"] = tools

        if model.supports_speculative and model.draft_model:
            payload["options"]["draft_model"] = model.draft_model

        payload.update(kwargs)

        with self._http.stream("POST", f"{self.host}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break


# ─── OpenAI-Compatible Backend (Cloud) ────────────────────────────────────────


class OpenAICompatibleBackend(Backend):
    """Cloud inference via any OpenAI-compatible API.

    Works with: OpenAI, Groq, OpenRouter, Together, vLLM servers, etc.
    """

    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        timeout: float = 120.0,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def is_available(self) -> bool:
        return bool(self.api_key)

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
        start = time.time()

        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} if "function" not in t else t for t in tools
            ]

        if response_format:
            payload["response_format"] = response_format

        payload.update(kwargs)

        resp = self._http.post(f"{self.base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        latency = (time.time() - start) * 1000
        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})

        return GenerateResponse(
            content=choice.get("message", {}).get("content", ""),
            model=model.name,
            provider=self.provider,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency,
            raw=data,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    def stream_chat(
        self,
        model: ModelInfo,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> Iterator[str]:
        payload: dict[str, Any] = {
            "model": model.name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} if "function" not in t else t for t in tools
            ]

        if response_format:
            payload["response_format"] = response_format

        payload.update(kwargs)

        with self._http.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line and line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue


# ─── LocalEngine Backend (Embedded, no LLM) ───────────────────────────────────


class LocalEngineBackend(Backend):
    """Backend wrapping the embedded LocalEngine.

    This is the zero-dependency, zero-cost, zero-latency backend.
    It handles text processing tasks (summarization, classification,
    extraction, simple Q&A, code generation) using deterministic algorithms.

    When it can't handle a request, it raises EngineCannotHandle so
    the client can fall back to Ollama or cloud.
    """

    def __init__(self):
        self.engine = LocalEngine()

    def is_available(self) -> bool:
        return True  # Always available

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
        start = time.time()

        # Extract intent and complexity from model tags or kwargs
        intent = kwargs.pop("_intent", "unknown")
        complexity = kwargs.pop("_complexity", "simple")

        result = self.engine.generate(
            messages=messages,
            intent=intent,
            complexity=complexity,
            response_format=response_format,
        )

        latency = (time.time() - start) * 1000

        if not result.handled:
            raise EngineCannotHandleError(
                f"LocalEngine cannot handle intent='{intent}' complexity='{complexity}'",
            )

        return GenerateResponse(
            content=result.content,
            model="local-engine",
            provider="engine",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=latency,
            raw={"method": result.method, "confidence": result.confidence},
            finish_reason="stop",
        )

    def stream_chat(
        self,
        model: ModelInfo,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        **kwargs,
    ) -> Iterator[str]:
        # Engine is so fast that streaming is pointless — just yield the whole thing
        result = self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
            **kwargs,
        )
        yield result.content


class EngineCannotHandleError(Exception):
    """Raised when the LocalEngine can't handle a request."""


# ─── Backend Factory ───────────────────────────────────────────────────────────

# Provider → base URL mapping
_PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
}


def create_backends(
    ollama_host: str = "http://localhost:11434",
    cloud_keys: dict[str, str | None] | None = None,
    timeout: float = 120.0,
    use_engine: bool = True,
) -> dict[str, Backend]:
    """Create all available backends based on configuration.

    Returns dict mapping provider name → Backend instance.
    Only includes backends that are available.

    Priority order (first available = default fallback):
    1. engine   — embedded deterministic text processing (always available, $0)
    2. ollama   — local LLM via Ollama ($0, needs install)
    3. cloud    — OpenAI-compatible APIs (priced per token)
    """
    backends: dict[str, Backend] = {}
    cloud_keys = cloud_keys or {}

    # Embedded engine — always available, zero dependencies
    if use_engine:
        backends["engine"] = LocalEngineBackend()

    # Ollama backend
    ollama = OllamaBackend(host=ollama_host, timeout=timeout)
    if ollama.is_available():
        backends["ollama"] = ollama

    # Cloud backends
    for provider, base_url in _PROVIDER_URLS.items():
        api_key = cloud_keys.get(provider)
        if api_key:
            backends[provider] = OpenAICompatibleBackend(
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )

    return backends
