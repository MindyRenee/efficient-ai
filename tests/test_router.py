"""
Tests for the router module — intent classification, complexity, and model selection.
"""

from efficient.models import CapabilityTier
from efficient.router import (
    Router,
    classify_intent,
    estimate_complexity,
    min_tier_for,
    select_model,
)


class TestIntentClassification:
    def test_classification_intent(self):
        msgs = [
            {
                "role": "user",
                "content": "Classify the sentiment of this review as positive or negative",
            }
        ]
        assert classify_intent(msgs) == "classification"

    def test_extraction_intent(self):
        msgs = [{"role": "user", "content": "Extract all email addresses from this text"}]
        assert classify_intent(msgs) == "extraction"

    def test_summarization_intent(self):
        msgs = [{"role": "user", "content": "Summarize this article in 3 bullet points"}]
        assert classify_intent(msgs) == "summarization"

    def test_simple_qa_intent(self):
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        assert classify_intent(msgs) == "simple_qa"

    def test_code_completion_intent(self):
        msgs = [{"role": "user", "content": "Write a Python function to sort a list"}]
        assert classify_intent(msgs) == "code_completion"

    def test_rag_intent(self):
        msgs = [{"role": "user", "content": "Based on the document, what is the revenue?"}]
        assert classify_intent(msgs) == "rag"

    def test_structured_generation_intent(self):
        msgs = [{"role": "user", "content": "Output the result in JSON format"}]
        assert classify_intent(msgs) == "structured_generation"

    def test_reasoning_intent(self):
        msgs = [
            {"role": "user", "content": "Why does the earth orbit the sun? Explain step by step."}
        ]
        assert classify_intent(msgs) == "reasoning"

    def test_agentic_intent(self):
        msgs = [{"role": "user", "content": "Plan and execute a web search workflow"}]
        assert classify_intent(msgs) == "agentic"

    def test_creative_intent(self):
        msgs = [{"role": "user", "content": "Write a short story about a robot"}]
        assert classify_intent(msgs) == "creative"

    def test_unknown_intent(self):
        msgs = [{"role": "user", "content": "xyzzy foobar quux"}]
        assert classify_intent(msgs) == "unknown"

    def test_empty_messages(self):
        assert classify_intent([]) == "unknown"

    def test_multi_message_uses_last_user(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "Summarize this text for me"},
        ]
        assert classify_intent(msgs) == "summarization"


class TestComplexityEstimation:
    def test_trivial(self):
        msgs = [{"role": "user", "content": "Hi"}]
        assert estimate_complexity(msgs) == "trivial"

    def test_simple(self):
        msgs = [
            {
                "role": "user",
                "content": "What is the capital of France and what river runs through it?",
            }
        ]
        assert estimate_complexity(msgs) == "simple"

    def test_moderate(self):
        msgs = [{"role": "user", "content": "Please explain how neural networks work. " * 20}]
        assert estimate_complexity(msgs) in ("moderate", "complex")

    def test_complex(self):
        # Long multi-turn with code
        msgs = [
            {
                "role": "user",
                "content": "First, analyze the code. Then, fix the bug. Finally, add tests.\n"
                + "line\n" * 200,
            },
            {"role": "assistant", "content": "I'll help with that."},
            {"role": "user", "content": "Here's the code:\n```python\n" + "x = 1\n" * 100 + "```"},
        ]
        assert estimate_complexity(msgs) == "complex"


class TestTierMapping:
    def test_classification_trivial_is_micro(self):
        assert min_tier_for("classification", "trivial") == CapabilityTier.MICRO

    def test_agentic_complex_is_frontier(self):
        assert min_tier_for("agentic", "complex") == CapabilityTier.FRONTIER

    def test_unknown_combo_defaults_to_mid(self):
        assert min_tier_for("nonexistent", "nonexistent") == CapabilityTier.MID


class TestModelSelection:
    def test_local_first_prefers_local(self):
        decision = select_model(
            intent="simple_qa",
            complexity="simple",
            tier=CapabilityTier.SMALL,
            vram_gb=16,
            available_local_models=["qwen2.5:7b", "llama3.1:8b"],
            available_providers=["openai"],
            local_first=True,
            preferred_local="qwen2.5:7b",
        )
        assert decision.model.is_local
        # Engine intercepts trivial/simple tasks before Ollama
        assert decision.model.name == "local-engine"

    def test_cloud_fallback_when_no_local(self):
        decision = select_model(
            intent="reasoning",
            complexity="complex",
            tier=CapabilityTier.LARGE,
            vram_gb=0,
            available_local_models=[],
            available_providers=["openai"],
            local_first=True,
            preferred_cloud="gpt-4o",
        )
        assert not decision.model.is_local
        assert decision.model.provider == "openai"

    def test_preferred_local_selected_when_capable(self):
        decision = select_model(
            intent="summarization",
            complexity="simple",
            tier=CapabilityTier.SMALL,
            vram_gb=32,
            available_local_models=["qwen2.5:7b", "qwen2.5:32b"],
            available_providers=[],
            local_first=True,
            preferred_local="qwen2.5:7b",
        )
        # Engine intercepts simple summarization before Ollama
        assert decision.model.name == "local-engine"

    def test_vram_filtering(self):
        """Models that don't fit in VRAM should not be selected."""
        decision = select_model(
            intent="reasoning",
            complexity="moderate",
            tier=CapabilityTier.MID,
            vram_gb=4,  # Very limited
            available_local_models=["qwen2.5:7b", "qwen2.5:32b", "phi3:mini"],
            available_providers=[],
            local_first=True,
            preferred_local="qwen2.5:32b",
        )
        # qwen2.5:32b needs 20GB, shouldn't be selected with 4GB VRAM
        assert decision.model.vram_required_gb <= 4

    def test_require_tools_filters(self):
        decision = select_model(
            intent="agentic",
            complexity="simple",
            tier=CapabilityTier.MID,
            vram_gb=32,
            available_local_models=["qwen2.5:7b", "deepseek-r1:14b"],
            available_providers=[],
            local_first=True,
            preferred_local="qwen2.5:7b",
            require_tools=True,
        )
        assert decision.model.supports_tools


class TestRouter:
    def test_full_routing_pipeline(self):
        router = Router(
            vram_gb=16,
            available_local_models=["qwen2.5:7b"],
            available_providers=["openai"],
            local_first=True,
            preferred_local="qwen2.5:7b",
        )
        decision = router.route(
            [
                {
                    "role": "user",
                    "content": "Summarize this text: The quick brown fox jumps over the lazy dog.",
                }
            ]
        )
        assert decision.intent == "summarization"
        assert decision.model.is_local
        # Engine intercepts simple summarization
        assert decision.model.name == "local-engine"

    def test_routing_esculates_to_cloud_for_complex(self):
        router = Router(
            vram_gb=0,
            available_local_models=[],
            available_providers=["openai"],
            local_first=True,
            preferred_cloud="gpt-4o",
        )
        decision = router.route(
            [
                {
                    "role": "user",
                    "content": "Plan and execute a complex multi-step agentic workflow with tool calls",
                }
            ]
        )
        assert not decision.model.is_local
        assert decision.model.provider == "openai"
