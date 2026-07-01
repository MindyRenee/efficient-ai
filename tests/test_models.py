"""
Tests for the models registry.
"""

import pytest
from efficient.models import (
    ModelInfo, CapabilityTier, all_models, local_models, cloud_models,
    models_by_tier, models_for_provider, get_model, cheapest_model_for_tier,
    best_local_model_for_vram, estimate_cost,
)


class TestModelRegistry:
    def test_all_models_not_empty(self):
        assert len(all_models()) > 10

    def test_local_models_include_engine(self):
        models = local_models()
        providers = {m.provider for m in models}
        assert "engine" in providers
        assert "ollama" in providers

    def test_local_models_are_free(self):
        for m in local_models():
            assert m.input_price_per_m == 0
            assert m.output_price_per_m == 0
            assert m.is_local

    def test_cloud_models_have_pricing(self):
        for m in cloud_models():
            assert m.input_price_per_m > 0
            assert m.output_price_per_m > 0
            assert not m.is_local

    def test_get_model_by_name(self):
        m = get_model("qwen2.5:7b")
        assert m is not None
        assert m.name == "qwen2.5:7b"
        assert m.tier == CapabilityTier.SMALL

    def test_get_model_not_found(self):
        assert get_model("nonexistent-model") is None

    def test_models_by_tier(self):
        small_models = models_by_tier(CapabilityTier.SMALL)
        assert len(small_models) > 0
        for m in small_models:
            assert m.tier == CapabilityTier.SMALL

    def test_models_for_provider(self):
        ollama_models = models_for_provider("ollama")
        assert len(ollama_models) > 0
        for m in ollama_models:
            assert m.provider == "ollama"

    def test_cheapest_model_for_tier(self):
        cheapest = cheapest_model_for_tier(CapabilityTier.MID)
        assert cheapest is not None
        # Local models are free, so cheapest should be local
        assert cheapest.is_local

    def test_best_local_model_for_vram(self):
        # 4GB VRAM should only fit phi3:mini
        model = best_local_model_for_vram(4.0)
        assert model is not None
        assert model.vram_required_gb <= 4.0

        # 48GB VRAM should fit the best model
        model = best_local_model_for_vram(48.0)
        assert model is not None
        assert model.mmlu_score >= 80  # Should pick a high-quality model

    def test_best_local_model_for_vram_with_tier(self):
        model = best_local_model_for_vram(48.0, CapabilityTier.LARGE)
        assert model is not None
        assert model.tier >= CapabilityTier.LARGE

    def test_estimate_cost_local(self):
        m = get_model("qwen2.5:7b")
        cost = estimate_cost(m, 1000, 500)
        assert cost == 0.0  # Local is free

    def test_estimate_cost_cloud(self):
        m = get_model("gpt-4o")
        cost = estimate_cost(m, 1_000_000, 1_000_000)
        expected = m.input_price_per_m + m.output_price_per_m
        assert cost == pytest.approx(expected)

    def test_quantization_info(self):
        for m in local_models():
            if m.provider == "ollama":
                assert m.quantization != ""
                assert m.vram_required_gb > 0

    def test_speculative_decoding_support(self):
        # At least one model should support speculative decoding
        spec_models = [m for m in local_models() if m.supports_speculative]
        assert len(spec_models) > 0
        for m in spec_models:
            assert m.draft_model != ""
