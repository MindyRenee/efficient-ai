"""Intent classifier and model router.

Classifies incoming requests by intent and complexity, then selects
the optimal model — local first, cloud fallback.

The classifier uses heuristics first (0ms, 0 cost) and only escalates
to a model-based classifier if heuristics are ambiguous.

Intent categories:
- classification: sentiment, category tagging, spam detection
- extraction: pulling structured data from text
- summarization: condensing longer text
- simple_qa: factual questions, lookups
- code_completion: code generation, completion
- rag: retrieval-augmented Q&A
- structured_generation: JSON output, formatting
- reasoning: multi-step logic, math
- agentic: tool use, multi-turn planning
- creative: writing, brainstorming
- unknown: unclassified, needs frontier

Complexity levels: trivial, simple, moderate, complex
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from efficient.models import (
    CapabilityTier,
    ModelInfo,
    cloud_models,
    get_model,
    local_models,
)


@dataclass
class RoutingDecision:
    """The result of a routing decision."""

    intent: str
    complexity: str  # trivial, simple, moderate, complex
    tier: CapabilityTier  # Minimum capability tier needed
    model: ModelInfo
    reason: str  # Human-readable explanation
    use_cache: bool = True
    use_speculative: bool = False


# ─── Intent Classification ────────────────────────────────────────────────────

# Keyword patterns for fast heuristic classification
_INTENT_PATTERNS: dict[str, list[re.Pattern]] = {
    "classification": [
        re.compile(r"\b(sentiment|classify|categor|spam|label|tag|detect)\b", re.IGNORECASE),
        re.compile(r"\b(positive|negative|neutral|spam|not spam)\b", re.IGNORECASE),
    ],
    "extraction": [
        re.compile(r"\b(extract|pull|parse|get the|find all|identify)\b", re.IGNORECASE),
        re.compile(
            r"\b(emails?|phones?|addresses?|names?|dates?|amounts?)\b.*\b(from|in)\b", re.IGNORECASE
        ),
    ],
    "summarization": [
        re.compile(r"\b(summari[sz]e|condense|tldr|brief|digest|abridged?)\b", re.IGNORECASE),
        re.compile(r"\b(key points?|main ideas?|takeaways?)\b", re.IGNORECASE),
    ],
    "simple_qa": [
        re.compile(r"^(what|when|where|who|how many|is|are|does|can)\b", re.IGNORECASE),
        re.compile(r"\b(define|meaning of|synonym|antonym)\b", re.IGNORECASE),
    ],
    "code_completion": [
        re.compile(r"\b(code|function|method|class|implement|debug|fix|refactor)\b", re.IGNORECASE),
        re.compile(r"\b(python|javascript|java|c\+\+|rust|go|sql|html|css)\b", re.IGNORECASE),
        re.compile(r"```", re.IGNORECASE),
    ],
    "rag": [
        re.compile(r"\b(based on (the )?(document|text|context|passage|article))\b", re.IGNORECASE),
        re.compile(r"\b(according to|from the (provided|given))\b", re.IGNORECASE),
    ],
    "structured_generation": [
        re.compile(r"\b(json|yaml|xml|csv|table|format|template)\b", re.IGNORECASE),
        re.compile(r"\b(output|respond|return) (in|as|with)\b", re.IGNORECASE),
    ],
    "reasoning": [
        re.compile(r"\b(why|explain|analyze|reason|deduce|infer|prove)\b", re.IGNORECASE),
        re.compile(r"\b(step.by.step|logically|therefore|thus|hence)\b", re.IGNORECASE),
        re.compile(r"\b(calculate|solve|math|equation|formula|probability)\b", re.IGNORECASE),
    ],
    "agentic": [
        re.compile(r"\b(plan|execute|run|call|tool|function call|agent|workflow)\b", re.IGNORECASE),
        re.compile(r"\b(search the web|browse|click|navigate|automate)\b", re.IGNORECASE),
    ],
    "creative": [
        re.compile(r"\b(write|story|poem|essay|article|blog|content|creative)\b", re.IGNORECASE),
        re.compile(r"\b(brainstorm|ideas?|imagine|draft|compose)\b", re.IGNORECASE),
    ],
}


def classify_intent(messages: list[dict]) -> str:
    """Classify the intent of a chat request.

    Uses heuristic pattern matching on the last user message.
    Falls back to "unknown" if no patterns match.
    """
    # Get the last user message
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                # Multi-modal content — extract text parts
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        user_text += part.get("text", "")
            break

    if not user_text:
        return "unknown"

    # Check each intent pattern
    scores: dict[str, int] = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            matches = pattern.findall(user_text)
            score += len(matches)
        if score > 0:
            scores[intent] = score

    if scores:
        return max(scores, key=lambda k: scores[k])  # type: ignore[arg-type]

    return "unknown"


# ─── Complexity Estimation ────────────────────────────────────────────────────


def estimate_complexity(messages: list[dict]) -> str:
    """Estimate the complexity of a request.

    Factors:
    - Total input length (tokens proxy: word count)
    - Number of messages in conversation
    - Presence of code blocks
    - Presence of multi-step instructions
    """
    total_words = 0
    msg_count = len(messages)
    has_multi_step = False

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_words += len(content.split())
            if re.search(r"\b(first|then|next|finally|step \d|step \d+)\b", content, re.IGNORECASE):
                has_multi_step = True
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    total_words += len(text.split())
                    if "```" in text:
                        pass  # Code detected

    # Complexity scoring
    if total_words < 10 and msg_count <= 2:
        return "trivial"
    if total_words < 50 and msg_count <= 3:
        return "simple"
    if total_words < 500 or (msg_count <= 5 and not has_multi_step):
        return "moderate"
    return "complex"


# ─── Tier Mapping ─────────────────────────────────────────────────────────────

# Map (intent, complexity) → minimum capability tier
_TIER_MAP: dict[tuple[str, str], CapabilityTier] = {
    # Classification — always low tier
    ("classification", "trivial"): CapabilityTier.MICRO,
    ("classification", "simple"): CapabilityTier.MICRO,
    ("classification", "moderate"): CapabilityTier.SMALL,
    ("classification", "complex"): CapabilityTier.SMALL,
    # Extraction — low tier
    ("extraction", "trivial"): CapabilityTier.MICRO,
    ("extraction", "simple"): CapabilityTier.SMALL,
    ("extraction", "moderate"): CapabilityTier.SMALL,
    ("extraction", "complex"): CapabilityTier.MID,
    # Summarization — low-mid tier
    ("summarization", "trivial"): CapabilityTier.SMALL,
    ("summarization", "simple"): CapabilityTier.SMALL,
    ("summarization", "moderate"): CapabilityTier.MID,
    ("summarization", "complex"): CapabilityTier.MID,
    # Simple Q&A — low tier
    ("simple_qa", "trivial"): CapabilityTier.MICRO,
    ("simple_qa", "simple"): CapabilityTier.SMALL,
    ("simple_qa", "moderate"): CapabilityTier.SMALL,
    ("simple_qa", "complex"): CapabilityTier.MID,
    # Code completion — mid tier
    ("code_completion", "trivial"): CapabilityTier.SMALL,
    ("code_completion", "simple"): CapabilityTier.SMALL,
    ("code_completion", "moderate"): CapabilityTier.MID,
    ("code_completion", "complex"): CapabilityTier.LARGE,
    # RAG — mid tier
    ("rag", "trivial"): CapabilityTier.SMALL,
    ("rag", "simple"): CapabilityTier.SMALL,
    ("rag", "moderate"): CapabilityTier.MID,
    ("rag", "complex"): CapabilityTier.MID,
    # Structured generation — low-mid tier
    ("structured_generation", "trivial"): CapabilityTier.SMALL,
    ("structured_generation", "simple"): CapabilityTier.SMALL,
    ("structured_generation", "moderate"): CapabilityTier.MID,
    ("structured_generation", "complex"): CapabilityTier.MID,
    # Reasoning — mid-high tier
    ("reasoning", "trivial"): CapabilityTier.SMALL,
    ("reasoning", "simple"): CapabilityTier.MID,
    ("reasoning", "moderate"): CapabilityTier.MID,
    ("reasoning", "complex"): CapabilityTier.LARGE,
    # Agentic — high tier
    ("agentic", "trivial"): CapabilityTier.MID,
    ("agentic", "simple"): CapabilityTier.MID,
    ("agentic", "moderate"): CapabilityTier.LARGE,
    ("agentic", "complex"): CapabilityTier.FRONTIER,
    # Creative — mid tier
    ("creative", "trivial"): CapabilityTier.SMALL,
    ("creative", "simple"): CapabilityTier.MID,
    ("creative", "moderate"): CapabilityTier.MID,
    ("creative", "complex"): CapabilityTier.LARGE,
    # Unknown — be conservative
    ("unknown", "trivial"): CapabilityTier.SMALL,
    ("unknown", "simple"): CapabilityTier.MID,
    ("unknown", "moderate"): CapabilityTier.MID,
    ("unknown", "complex"): CapabilityTier.FRONTIER,
}


def min_tier_for(intent: str, complexity: str) -> CapabilityTier:
    """Get the minimum capability tier for an intent+complexity combination."""
    return _TIER_MAP.get(
        (intent, complexity),
        CapabilityTier.MID,  # Default to mid if unknown combo
    )


# ─── Model Selection ──────────────────────────────────────────────────────────


def select_model(
    intent: str,
    complexity: str,
    tier: CapabilityTier,
    vram_gb: float = 0,
    available_local_models: list[str] | None = None,
    available_providers: list[str] | None = None,
    local_first: bool = True,
    preferred_local: str = "",
    preferred_cloud: str = "gpt-4o-mini",
    fallback_cloud: str = "gpt-4o",
    require_tools: bool = False,
    require_vision: bool = False,
    require_json: bool = False,
) -> RoutingDecision:
    """Select the best model for a request.

    Strategy:
    1. If local-first and a capable local model is available → use it
    2. If no local model fits or is capable → use cheapest cloud model at tier
    3. If no cloud model available → fall back to best available local
    """
    available_local_models = available_local_models or []
    available_providers = available_providers or []

    # 0. Try the embedded engine first for trivial/simple tasks
    #    The engine is zero-cost, zero-latency, and always available.
    #    It handles: summarization, classification, extraction, simple_qa,
    #    code_completion, structured_generation at trivial/simple complexity.
    if local_first and not require_vision and not require_tools:
        from efficient.local_engine import LocalEngine

        engine = LocalEngine()
        if engine.can_handle(intent, complexity):
            from efficient.models import _ENGINE_MODEL

            return RoutingDecision(
                intent=intent,
                complexity=complexity,
                tier=tier,
                model=_ENGINE_MODEL,
                reason=f"Embedded engine can handle '{intent}' at '{complexity}' complexity (0ms, $0)",
                use_cache=True,
            )

    # Filter local models by availability and requirements
    local_candidates = []
    for m in local_models():
        if m.name not in available_local_models and preferred_local not in available_local_models:
            continue
        if m.tier < tier:
            continue
        if require_tools and not m.supports_tools:
            continue
        if require_vision and not m.supports_vision:
            continue
        if require_json and not m.supports_json:
            continue
        if vram_gb > 0 and m.vram_required_gb > vram_gb:
            continue
        local_candidates.append(m)

    # If preferred local model is available and capable, use it
    if local_first and local_candidates:
        # Sort by: preferred first, then by capability (lowest tier that meets requirements = cheapest)
        preferred_match = None
        for m in local_candidates:
            if m.name == preferred_local or m.name.startswith(
                preferred_local.split(":", maxsplit=1)[0]
            ):
                preferred_match = m
                break

        if preferred_match:
            return RoutingDecision(
                intent=intent,
                complexity=complexity,
                tier=tier,
                model=preferred_match,
                reason=f"Local model '{preferred_match.name}' available and meets tier {tier.name} requirement",
                use_cache=True,
                use_speculative=preferred_match.supports_speculative,
            )

        # Otherwise pick the cheapest capable local model
        best = min(local_candidates, key=lambda m: (m.tier, -m.mmlu_score))
        return RoutingDecision(
            intent=intent,
            complexity=complexity,
            tier=tier,
            model=best,
            reason=f"Local model '{best.name}' is cheapest available at tier {tier.name}+",
            use_cache=True,
            use_speculative=best.supports_speculative,
        )

    # Cloud fallback — find cheapest cloud model at tier
    cloud_candidates = []
    for m in cloud_models():
        if m.tier < tier:
            continue
        if available_providers and m.provider not in available_providers:
            continue
        if require_tools and not m.supports_tools:
            continue
        if require_vision and not m.supports_vision:
            continue
        if require_json and not m.supports_json:
            continue
        cloud_candidates.append(m)

    if cloud_candidates:
        # Prefer the configured preferred cloud model if it matches
        for m in cloud_candidates:
            if m.name == preferred_cloud:
                return RoutingDecision(
                    intent=intent,
                    complexity=complexity,
                    tier=tier,
                    model=m,
                    reason=f"Cloud model '{m.name}' (preferred) at tier {tier.name}+",
                    use_cache=True,
                )

        # Cheapest cloud model at tier
        best = min(cloud_candidates, key=lambda m: m.avg_price_per_m)
        return RoutingDecision(
            intent=intent,
            complexity=complexity,
            tier=tier,
            model=best,
            reason=f"Cloud model '{best.name}' is cheapest available at tier {tier.name}+",
            use_cache=True,
        )

    # Last resort: fallback cloud model
    fallback = get_model(fallback_cloud)
    if fallback:
        return RoutingDecision(
            intent=intent,
            complexity=complexity,
            tier=tier,
            model=fallback,
            reason=f"Fallback cloud model '{fallback.name}' — no optimal match found",
            use_cache=True,
        )

    # Absolute last resort: first local model
    if local_models():
        m = local_models()[0]
        return RoutingDecision(
            intent=intent,
            complexity=complexity,
            tier=tier,
            model=m,
            reason=f"Emergency fallback to local model '{m.name}'",
            use_cache=True,
        )

    raise RuntimeError("No models available for routing")


class Router:
    """The main routing engine. Combines intent classification, complexity
    estimation, and model selection into one decision.
    """

    def __init__(
        self,
        vram_gb: float = 0,
        available_local_models: list[str] | None = None,
        available_providers: list[str] | None = None,
        local_first: bool = True,
        preferred_local: str = "",
        preferred_cloud: str = "gpt-4o-mini",
        fallback_cloud: str = "gpt-4o",
    ):
        self.vram_gb = vram_gb
        self.available_local_models = available_local_models or []
        self.available_providers = available_providers or []
        self.local_first = local_first
        self.preferred_local = preferred_local
        self.preferred_cloud = preferred_cloud
        self.fallback_cloud = fallback_cloud

    def route(
        self,
        messages: list[dict],
        require_tools: bool = False,
        require_vision: bool = False,
        require_json: bool = False,
    ) -> RoutingDecision:
        """Route a request to the optimal model.

        Args:
            messages: OpenAI-format chat messages
            require_tools: Whether the request needs tool/function calling
            require_vision: Whether the request needs vision capability
            require_json: Whether the request needs JSON output

        Returns:
            RoutingDecision with the selected model and reasoning

        """
        intent = classify_intent(messages)
        complexity = estimate_complexity(messages)
        tier = min_tier_for(intent, complexity)

        return select_model(
            intent=intent,
            complexity=complexity,
            tier=tier,
            vram_gb=self.vram_gb,
            available_local_models=self.available_local_models,
            available_providers=self.available_providers,
            local_first=self.local_first,
            preferred_local=self.preferred_local,
            preferred_cloud=self.preferred_cloud,
            fallback_cloud=self.fallback_cloud,
            require_tools=require_tools,
            require_vision=require_vision,
            require_json=require_json,
        )
