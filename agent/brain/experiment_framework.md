---
name: Experiment Framework
version: 2.0
last_updated: 2026-07-02
---

# Experimentation Framework

How to test routing, caching, and optimization improvements.

## Experiment Structure

```markdown
---
experiment_id: unique_id
hypothesis: clear_statement
start_date: ISO8601
end_date: ISO8601
status: running|completed|failed
metrics:
  - metric_name
  - baseline_value
  - target_value
results:
  - actual_value
  - improvement_percentage
lessons_learned: string
---
```

## Experiment Types

### 1. Cache Optimization

- Similarity threshold tuning (0.85 vs 0.92 vs 0.95)
- Embedding model comparison (nomic-embed-text vs hash-based)
- Pre-warm strategies (top 50 vs top 100 vs top 500 queries)
- TTL impact (no TTL vs 1h vs 24h)

### 2. Intent Classification Accuracy

- New heuristic patterns for emerging query types
- Regex vs keyword vs embedding classification
- Bypass LUT size (10 vs 20 vs 50 entries)
- Classification latency vs accuracy tradeoff

### 3. Engine Coverage Expansion

- Add new deterministic handlers (top 3 failure clusters)
- Algorithm selection (Naive Bayes vs TF-IDF vs regex)
- Handler accuracy per intent sub-type
- False positive rate (engine claiming it can handle but failing)

### 4. Model Selection Strategy

- Tier threshold adjustments (what qualifies as "moderate")
- VRAM-aware routing (load 2 models vs 3)
- Quantization level per intent (Q4 vs Q5 vs Q8)
- Speculative decoding acceptance rate by model pair

### 5. x402 Pricing Optimization

- Tiered pricing vs flat pricing
- Per-request transparency vs bundled pricing
- Minimum viable payment threshold
- Conversion rate by price point

### 6. Cloud Provider Selection

- Price polling frequency (hourly vs daily)
- Provider priority order (Groq vs OpenAI vs OpenRouter)
- Fallback behavior on provider failure
- Volume discount negotiation thresholds

## Experiment Rules

- Run in production with real traffic (A/B on a subset)
- Minimum 1000 requests per variant
- Track all metrics in telemetry (not just primary)
- Roll back if p95 latency degrades >20%
- Document negative results

## Success Criteria

- **Cache**: +5% hit rate with no latency increase
- **Classification**: -0.1ms routing time with no accuracy loss
- **Engine**: +2% coverage with no false positive increase
- **Model**: -10% cost with no quality degradation
- **x402**: +20% revenue per endpoint
- **Provider**: -15% cloud cost with same quality

## Threshold Triggers

- If cache hit rate drops >5%: Revert similarity threshold
- If engine false positive >2%: Tighten can_handle logic
- If cloud fallback >10% for 24h: Investigate Ollama health
- If x402 conversion <1%: Lower minimum payment

## Tracking

All experiments logged in telemetry with `experiment_id` tag.
Results feed back into `alpha_strategies.md` and `configuration.md`.
