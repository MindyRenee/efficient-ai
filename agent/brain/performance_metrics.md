---
name: Performance Metrics
---

# Performance Metrics

What Efficient AI tracks and how to measure success.

## Core Metrics

### Cost Metrics

- **Total Cost**: Sum of all cloud API spend
- **Cost per Request**: Average across all backends
- **Savings vs Frontier**: frontier_cost - actual_cost
- **Free Query Rate**: % served by engine or Ollama
- **Cloud Dependency**: % hitting cloud fallback (target: <5%)

### Latency Metrics

- **p50 Latency**: 50th percentile response time
- **p95 Latency**: 95th percentile (catches outliers)
- **Engine Latency**: <1ms target
- **Ollama Latency**: 50-500ms target
- **Cloud Latency**: 500-2000ms expected

### Routing Metrics

- **Cache Hit Rate**: 30-50% target
- **Engine Coverage**: % queries handled by deterministic layer
- **Ollama Adoption**: % queries routed to local LLM
- **Cloud Fallback Rate**: % queries sent to external APIs
- **Fallback Frequency**: How often engine → Ollama → cloud chain is used

### Backend Health

- **Ollama Uptime**: % time Ollama is available
- **Model Load Time**: Time to load model into VRAM
- **GPU Utilization**: VRAM usage per model
- **Cloud API Success Rate**: % successful calls per provider

## Tracking Frequency

### Per Request

- Provider used (engine, ollama, openai, groq, openrouter)
- Model name and tier
- Input/output tokens
- Latency (ms)
- Cost ($)
- Cache hit (boolean)
- Intent and complexity

### Hourly

- Requests per backend
- Average latency per backend
- Error rate per backend
- Cache hit rate (rolling window)

### Daily

- Total cost and savings
- Backend breakdown pie chart
- Engine coverage percentage
- x402 revenue (if enabled)

### Weekly

- Trend analysis (cost, latency, coverage)
- Model performance comparison
- Failure pattern clustering
- Engine expansion opportunities

## Targets

### Month 1

- Engine coverage: 80%
- Cache hit rate: 20%
- Cloud fallback: <15%
- Avg latency (p50): <100ms

### Month 3

- Engine coverage: 85%
- Cache hit rate: 35%
- Cloud fallback: <8%
- Avg latency (p50): <50ms

### Month 6

- Engine coverage: 90%
- Cache hit rate: 45%
- Cloud fallback: <5%
- Avg latency (p50): <10ms

### Month 12

- Engine coverage: 95%
- Cache hit rate: 50%
- Cloud fallback: <3%
- Avg latency (p50): <5ms

## Alert Thresholds

### Warnings

- Cloud fallback > 10% for 24h
- Ollama uptime < 95%
- Cache hit rate < 15%
- p95 latency > 1000ms

### Critical

- No backends available for > 5 minutes
- SQLite corruption detected
- x402 double-spend detected
- Cost > $10/day unexpectedly
