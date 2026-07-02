"""Model registry — capability tiers, pricing, and quantization awareness.

Defines the model universe that the router selects from, organized by
capability tier (micro, small, mid, large, frontier) with real-world
pricing data as of June 2026.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class CapabilityTier(IntEnum):
    """Model capability tiers, ordered from cheapest to most expensive."""

    MICRO = 0  # <2B params — classification, extraction, validation
    SMALL = 1  # 2-8B params — summarization, simple Q&A, code completion
    MID = 2  # 8-32B params — structured generation, RAG, tool use
    LARGE = 3  # 32-70B params — complex reasoning, agentic workflows
    FRONTIER = 4  # 70B+ / proprietary — hardest reasoning, long-horizon agents


@dataclass
class ModelInfo:
    """Information about a specific model."""

    name: str  # Canonical name
    tier: CapabilityTier
    provider: str  # ollama, openai, groq, openrouter, together, etc.
    param_count_b: float = 0  # Billions of parameters (0 for proprietary)
    context_window: int = 4096
    # Pricing per million tokens (USD), 0 for local
    input_price_per_m: float = 0.0
    output_price_per_m: float = 0.0
    # Quality benchmarks (0-100 scale, normalized)
    mmlu_score: float = 0.0
    human_eval: float = 0.0
    # Capabilities
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json: bool = False
    # Local model info
    quantization: str = ""  # e.g. "Q4_K_M"
    vram_required_gb: float = 0  # At stated quantization
    # Speculative decoding support
    supports_speculative: bool = False
    draft_model: str = ""  # Companion draft model for spec decoding
    # Misc
    max_output_tokens: int = 4096
    tags: list[str] = field(default_factory=list)

    @property
    def is_local(self) -> bool:
        return self.provider in ("ollama", "engine")

    @property
    def avg_price_per_m(self) -> float:
        """Average of input and output price per million tokens."""
        return (self.input_price_per_m + self.output_price_per_m) / 2


# ─── Model Registry ────────────────────────────────────────────────────────────

# Embedded engine — zero-cost, zero-dependency, always available
_ENGINE_MODEL = ModelInfo(
    name="local-engine",
    tier=CapabilityTier.MICRO,
    provider="engine",
    param_count_b=0,
    context_window=100000,
    mmlu_score=0,
    human_eval=0,
    supports_json=True,
    supports_tools=False,
    quantization="none",
    vram_required_gb=0,
    max_output_tokens=4096,
    tags=[
        "summarization",
        "classification",
        "extraction",
        "simple-qa",
        "code-completion",
        "structured-generation",
        "embedded",
        "zero-cost",
    ],
)

# Local models (Ollama) — $0/token, run on your hardware
_LOCAL_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="phi3:mini",
        tier=CapabilityTier.MICRO,
        provider="ollama",
        param_count_b=3.8,
        context_window=128000,
        mmlu_score=68.0,
        human_eval=62.0,
        supports_json=True,
        supports_tools=False,
        quantization="Q4_K_M",
        vram_required_gb=2.3,
        max_output_tokens=4096,
        tags=["classification", "extraction", "validation", "fast"],
    ),
    ModelInfo(
        name="gemma2:9b",
        tier=CapabilityTier.SMALL,
        provider="ollama",
        param_count_b=9.0,
        context_window=8192,
        mmlu_score=71.0,
        human_eval=60.0,
        supports_json=True,
        supports_tools=False,
        quantization="Q4_K_M",
        vram_required_gb=5.5,
        max_output_tokens=4096,
        tags=["summarization", "simple-qa", "fast"],
    ),
    ModelInfo(
        name="qwen2.5:7b",
        tier=CapabilityTier.SMALL,
        provider="ollama",
        param_count_b=7.0,
        context_window=128000,
        mmlu_score=74.0,
        human_eval=72.0,
        supports_json=True,
        supports_tools=True,
        quantization="Q4_K_M",
        vram_required_gb=4.5,
        supports_speculative=True,
        draft_model="qwen2.5:0.5b",
        max_output_tokens=8192,
        tags=["summarization", "code-completion", "rag", "tools", "fast"],
    ),
    ModelInfo(
        name="llama3.1:8b",
        tier=CapabilityTier.SMALL,
        provider="ollama",
        param_count_b=8.0,
        context_window=128000,
        mmlu_score=73.0,
        human_eval=72.0,
        supports_json=True,
        supports_tools=True,
        quantization="Q4_K_M",
        vram_required_gb=5.0,
        max_output_tokens=8192,
        tags=["summarization", "rag", "tools", "general"],
    ),
    ModelInfo(
        name="deepseek-r1:7b",
        tier=CapabilityTier.SMALL,
        provider="ollama",
        param_count_b=7.0,
        context_window=64000,
        mmlu_score=74.0,
        human_eval=70.0,
        supports_json=True,
        supports_tools=False,
        quantization="Q4_K_M",
        vram_required_gb=4.5,
        max_output_tokens=8192,
        tags=["reasoning", "math", "code"],
    ),
    ModelInfo(
        name="qwen2.5:14b",
        tier=CapabilityTier.MID,
        provider="ollama",
        param_count_b=14.0,
        context_window=128000,
        mmlu_score=79.0,
        human_eval=78.0,
        supports_json=True,
        supports_tools=True,
        quantization="Q4_K_M",
        vram_required_gb=9.0,
        supports_speculative=True,
        draft_model="qwen2.5:0.5b",
        max_output_tokens=8192,
        tags=["rag", "tool-use", "structured-generation", "code"],
    ),
    ModelInfo(
        name="deepseek-r1:14b",
        tier=CapabilityTier.MID,
        provider="ollama",
        param_count_b=14.0,
        context_window=64000,
        mmlu_score=82.0,
        human_eval=76.0,
        supports_json=True,
        supports_tools=False,
        quantization="Q4_K_M",
        vram_required_gb=9.0,
        max_output_tokens=8192,
        tags=["reasoning", "math", "complex-analysis"],
    ),
    ModelInfo(
        name="qwen2.5:32b",
        tier=CapabilityTier.MID,
        provider="ollama",
        param_count_b=32.0,
        context_window=128000,
        mmlu_score=83.2,
        human_eval=84.0,
        supports_json=True,
        supports_tools=True,
        quantization="Q4_K_M",
        vram_required_gb=20.0,
        supports_speculative=True,
        draft_model="qwen2.5:0.5b",
        max_output_tokens=8192,
        tags=["agentic", "complex-reasoning", "code", "rag"],
    ),
    ModelInfo(
        name="llama3.3:70b",
        tier=CapabilityTier.LARGE,
        provider="ollama",
        param_count_b=70.0,
        context_window=128000,
        mmlu_score=83.1,
        human_eval=82.0,
        supports_json=True,
        supports_tools=True,
        quantization="Q4_K_M",
        vram_required_gb=40.0,
        max_output_tokens=8192,
        tags=["agentic", "complex-reasoning", "frontier-adjacent"],
    ),
]

# Cloud models — priced per million tokens
_CLOUD_MODELS: list[ModelInfo] = [
    # OpenAI
    ModelInfo(
        name="gpt-4o-mini",
        tier=CapabilityTier.SMALL,
        provider="openai",
        context_window=128000,
        input_price_per_m=0.15,
        output_price_per_m=0.60,
        mmlu_score=82.0,
        human_eval=87.0,
        supports_tools=True,
        supports_vision=True,
        supports_json=True,
        max_output_tokens=16384,
        tags=["general", "fast", "cheap-cloud"],
    ),
    ModelInfo(
        name="gpt-4o",
        tier=CapabilityTier.LARGE,
        provider="openai",
        context_window=128000,
        input_price_per_m=2.50,
        output_price_per_m=10.00,
        mmlu_score=88.0,
        human_eval=91.0,
        supports_tools=True,
        supports_vision=True,
        supports_json=True,
        max_output_tokens=16384,
        tags=["reasoning", "agentic", "vision"],
    ),
    ModelInfo(
        name="gpt-4",
        tier=CapabilityTier.LARGE,
        provider="openai",
        context_window=128000,
        input_price_per_m=2.50,
        output_price_per_m=10.00,
        mmlu_score=86.0,
        human_eval=89.0,
        supports_tools=True,
        supports_vision=False,
        supports_json=True,
        max_output_tokens=16384,
        tags=["reasoning", "agentic", "legacy"],
    ),
    ModelInfo(
        name="gpt-5",
        tier=CapabilityTier.FRONTIER,
        provider="openai",
        context_window=256000,
        input_price_per_m=5.00,
        output_price_per_m=15.00,
        mmlu_score=90.0,
        human_eval=93.0,
        supports_tools=True,
        supports_vision=True,
        supports_json=True,
        max_output_tokens=32768,
        tags=["frontier", "reasoning", "agentic", "vision"],
    ),
    ModelInfo(
        name="gpt-3.5-turbo",
        tier=CapabilityTier.SMALL,
        provider="openai",
        context_window=16384,
        input_price_per_m=0.50,
        output_price_per_m=1.50,
        mmlu_score=71.0,
        human_eval=78.0,
        supports_tools=True,
        supports_vision=False,
        supports_json=True,
        max_output_tokens=4096,
        tags=["general", "fast", "legacy"],
    ),
    # Groq (ultra-fast inference)
    ModelInfo(
        name="llama-3.3-70b-versatile",
        tier=CapabilityTier.LARGE,
        provider="groq",
        context_window=128000,
        input_price_per_m=0.59,
        output_price_per_m=0.79,
        mmlu_score=83.1,
        human_eval=82.0,
        supports_tools=True,
        supports_json=True,
        max_output_tokens=32768,
        tags=["fast", "cheap-cloud", "general"],
    ),
    ModelInfo(
        name="deepseek-v4-flash",
        tier=CapabilityTier.MID,
        provider="groq",
        context_window=64000,
        input_price_per_m=0.14,
        output_price_per_m=0.28,
        mmlu_score=80.0,
        human_eval=78.0,
        supports_tools=True,
        supports_json=True,
        max_output_tokens=8192,
        tags=["fast", "ultra-cheap", "agentic"],
    ),
    # OpenRouter (aggregator — provides access to many models)
    ModelInfo(
        name="deepseek/deepseek-v4-flash",
        tier=CapabilityTier.MID,
        provider="openrouter",
        context_window=64000,
        input_price_per_m=0.14,
        output_price_per_m=0.28,
        mmlu_score=80.0,
        human_eval=78.0,
        supports_tools=True,
        supports_json=True,
        max_output_tokens=8192,
        tags=["ultra-cheap", "agentic", "general"],
    ),
    ModelInfo(
        name="qwen/qwen-4-72b",
        tier=CapabilityTier.LARGE,
        provider="openrouter",
        context_window=128000,
        input_price_per_m=0.45,
        output_price_per_m=1.20,
        mmlu_score=84.0,
        human_eval=86.0,
        supports_tools=True,
        supports_json=True,
        max_output_tokens=8192,
        tags=["cheap-cloud", "reasoning", "code"],
    ),
]


# ─── Registry API ──────────────────────────────────────────────────────────────


def all_models() -> list[ModelInfo]:
    """Return all registered models."""
    return _LOCAL_MODELS + _CLOUD_MODELS


def local_models() -> list[ModelInfo]:
    """Return all local models (engine + Ollama)."""
    return [_ENGINE_MODEL] + _LOCAL_MODELS


def cloud_models() -> list[ModelInfo]:
    """Return all cloud models."""
    return _CLOUD_MODELS


def models_by_tier(tier: CapabilityTier) -> list[ModelInfo]:
    """Return all models at a given capability tier."""
    return [m for m in all_models() if m.tier == tier]


def models_for_provider(provider: str) -> list[ModelInfo]:
    """Return all models for a given provider."""
    return [m for m in all_models() if m.provider == provider]


def get_model(name: str) -> ModelInfo | None:
    """Look up a model by name. Returns None if not found."""
    for m in all_models():
        if m.name == name:
            return m
    return None


def cheapest_model_for_tier(tier: CapabilityTier, provider: str | None = None) -> ModelInfo | None:
    """Return the cheapest model at or above a given tier."""
    candidates = [m for m in all_models() if m.tier >= tier]
    if provider:
        candidates = [m for m in candidates if m.provider == provider]
    if not candidates:
        return None
    return min(candidates, key=lambda m: m.avg_price_per_m)


def best_local_model_for_vram(
    vram_gb: float, tier: CapabilityTier | None = None
) -> ModelInfo | None:
    """Return the best local model that fits in the given VRAM.
    If tier is specified, return the best model at that tier that fits.
    """
    candidates = [m for m in _LOCAL_MODELS if m.vram_required_gb <= vram_gb]
    if tier is not None:
        candidates = [m for m in candidates if m.tier >= tier]
    if not candidates:
        return None
    # Best = highest MMLU score that fits
    return max(candidates, key=lambda m: m.mmlu_score)


def estimate_cost(model: ModelInfo, input_tokens: int, output_tokens: int) -> float:
    """Estimate the dollar cost of a request."""
    return (input_tokens / 1_000_000) * model.input_price_per_m + (
        output_tokens / 1_000_000
    ) * model.output_price_per_m
