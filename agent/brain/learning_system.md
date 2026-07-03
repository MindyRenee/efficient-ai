---
name: Learning System
---

# Learning System

How Efficient AI improves routing, coverage, and cost over time.

## Learning Sources

### 1. Engine Failure Patterns

- Query telemetry for `provider != "engine"` where engine could have handled
- Cluster by intent + complexity + query keywords
- Top 3 clusters become next engine expansion targets
- Target: 85% → 90% → 95% coverage

### 2. Cache Miss Analysis

- Log queries that missed cache but were repeated within 24h
- Identify paraphrase gaps
- Add to pre-warm set
- Track hit rate improvement per addition

### 3. Classification Errors

- Wrong intent classification leads to wrong backend
- Track: engine routed to Ollama unnecessarily
- Track: Ollama routed to cloud unnecessarily
- Adjust heuristic patterns based on misclassifications

### 4. User Override Patterns

- When human forces `model=` parameter, log intent + forced model
- If pattern emerges (e.g., always force Ollama for "code"), update tier map
- Respect user preference while optimizing defaults

## Improvement Cycle

### Weekly

1. Query telemetry for top 20 failure clusters
2. Implement 1-3 new engine handlers
3. Update intent classifier with new patterns
4. Adjust cache pre-warm set
5. Measure: coverage %, hit rate %, avg latency

### Monthly

1. Review cost trends vs frontier baseline
2. Evaluate model registry (new Ollama releases?)
3. Benchmark quantization levels per intent
4. Update `alpha_strategies.md` with new findings
5. Publish impact report

## Success Metrics

- Engine coverage growth: +2% per month target
- Cache hit rate: +5% per month target
- Classification accuracy: >95% target
- Cost reduction: -10% per month target
