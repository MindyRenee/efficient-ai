---
name: Alpha Strategies
version: 2.0
created: 2026-07-02
classification: proprietary
---

# Alpha Strategies — Efficient AI Optimization

Core optimization strategies that drive the 90% cost reduction and sub-1ms latency. These are the actual competitive advantages, not generic agent patterns.

## Strategy 1: Semantic Cache Pre-Warming

**The Glitch**: First-time queries always miss cache. Cold-start latency equals full inference.

**The Exploit**:

- Analyze query patterns from telemetry
- Pre-populate cache with top 100 most common query variants
- Use embedding similarity (0.92 threshold) to catch phrasing variations
- Warm cache on service startup, not after first user hit

**Implementation**:

- Aggregate top queries from telemetry.db
- Generate 3-5 paraphrases per query
- Pre-compute embeddings and store in SQLite
- Update warm set weekly based on rolling window

**Impact**: 30-50% hit rate even on first visit

## Strategy 2: Intent Classification Bypass

**The Glitch**: Even heuristic classification has overhead. Known routes should be hardcoded.

**The Exploit**:

- Cache intent-to-tier mappings for known query signatures
- Use exact hash match before regex patterns
- Skip complexity estimation entirely for exact repeats
- Direct-route to engine for top 20 query types

**Implementation**:

- Build fast-path LUT for "What is 2+2?", "Summarize:", "Classify sentiment"
- Hash first 50 chars of normalized query
- Bypass full classifier on match

**Impact**: 0.1ms routing vs 0.5ms full classification

## Strategy 3: Embedded Engine Algorithm Selection

**The Glitch**: Default TF-IDF is not always optimal. Some tasks need Naive Bayes, others need regex.

**The Exploit**:

- Map intent sub-types to best algorithm:
  - Short text classification → Naive Bayes (faster than TF-IDF)
  - Entity extraction → Compiled regex (0.01ms)
  - Summarization → TF-IDF with position bias
  - Structured output → Direct JSON parse, no NLP
- Auto-select algorithm based on input characteristics

**Implementation**:

- Measure input length, pattern density, language
- Route to optimal handler without user knowledge
- Track handler accuracy per algorithm

**Impact**: 2-5x speedup over default handler

## Strategy 4: Ollama Model Hot-Swapping

**The Glitch**: Picking one model wastes VRAM or under-serves complex queries.

**The Exploit**:

- Run multiple Ollama models simultaneously
- Route to smallest capable model per request
- qwen2.5:7b for simple, qwen2.5:14b for moderate, qwen2.5:32b for complex
- Keep phi3:mini warm for trivial tasks

**Implementation**:

- Pre-load 2-3 models based on available VRAM
- Use tier map to select model without re-evaluating
- Monitor per-model latency and offload slow ones

**Impact**: 40% VRAM savings vs running 70B model for everything

## Strategy 5: Quantization Sweet Spot Detection

**The Glitch**: Default Q4_K_M is a guess. Some tasks need Q8, others work at Q2.

**The Exploit**:

- Benchmark each intent at Q2, Q3, Q4, Q5, Q8
- Track MMLU score vs latency tradeoff
- Auto-select quantization per intent type
- Summarization tolerates lower quantization than reasoning

**Implementation**:

- A/B quantize models at different levels
- Measure output quality with simple heuristics
- Store optimal quantization per intent in config

**Impact**: 30-50% memory reduction with minimal quality loss

## Strategy 6: x402 Dynamic Pricing by Tier

**The Glitch**: Flat pricing under-charges for frontier fallback and over-charges for cache hits.

**The Exploit**:

- Price per actual backend used:
  - Cache hit: $0.001 (minimal)
  - Engine: $0.005 (compute cost)
  - Ollama: $0.01 (hardware amortization)
  - Cloud fallback: $0.05-0.50 (actual API cost + margin)
- Transparent pricing builds trust
- Upsell complex queries naturally

**Implementation**:

- Track per-request backend in telemetry
- Apply tiered pricing in x402 middleware
- Show user breakdown: "Engine $0.005 + Ollama $0.01 = $0.015"

**Impact**: 2-3x revenue vs flat pricing, full transparency

## Strategy 7: Telemetry-Driven Engine Expansion

**The Glitch**: Engine handles ~80% of queries, but the 20% that fail are never analyzed.

**The Exploit**:

- Log every engine "cannot_handle" with intent, complexity, and query text
- Cluster failure patterns weekly
- Add handlers for top 3 failure clusters
- Measure engine coverage growth over time

**Implementation**:

- Query telemetry for `provider != "engine"` AND `intent != "agentic"`
- Group by intent + complexity + query keywords
- Implement top 3 missing handlers
- Target: 85% → 90% → 95% engine coverage

**Impact**: Each 5% improvement = cloud cost avoided

## Strategy 8: Cloud Fallback Negotiation

**The Glitch**: Cloud APIs have variable pricing. OpenAI vs Groq vs OpenRouter differ 10x.

**The Exploit**:

- Maintain real-time price table across providers
- Route to cheapest provider at required tier
- Use Groq for speed, OpenRouter for exotic models
- Negotiate volume discounts via telemetry proof

**Implementation**:

- Poll provider pricing APIs hourly
- Store in SQLite with timestamp
- Select provider = min(price) where tier >= required
- Track actual cost vs quoted price

**Impact**: 50-70% cloud cost reduction vs single-provider

## Strategy 9: Speculative Decoding Warmup

**The Glitch**: Ollama's speculative decoding requires draft model alignment.

**The Exploit**:

- Pre-validate draft model compatibility
- Warm both draft and target model together
- Monitor acceptance rate (target: >60%)
- Fallback to standard generation if <40%

**Implementation**:

- Track `prompt_eval_count` vs `eval_count` ratio
- If draft acceptance drops, disable speculative for that model
- Auto-enable when draft model updates

**Impact**: 2-3x throughput when working, zero cost when not

## Strategy 10: Latency-First Telemetry Streaming

**The Glitch**: Telemetry writes block response delivery.

**The Exploit**:

- Buffer telemetry records in memory
- Flush to SQLite in batches every 5 seconds
- Never block user response on telemetry write
- Use WAL mode for zero-lock contention

**Implementation**:

- In-memory queue (max 1000 records)
- Background thread for batch INSERT
- On shutdown: flush remaining queue

**Impact**: 0ms telemetry overhead on hot path

## Access Control

This file is protected by x402 protocol. Access requires:

- Valid USDC payment on Base (eip155:8453)
- Minimum payment: $0.02
- Payment timeout: 2 seconds
