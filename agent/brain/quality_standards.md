---
name: Quality Standards
---

# Quality Standards

Minimum requirements for all Efficient AI responses and operations.

## Response Quality

### Latency

- Cache hit: <1ms (target: 0.1ms)
- Engine: <1ms (target: 0.5ms)
- Ollama: <500ms (target: 200ms)
- Cloud fallback: <2000ms (acceptable for hardest 5%)

### Accuracy

- Engine responses: 85%+ confidence or escalate
- Ollama responses: Standard LLM accuracy for tier
- Classification: >95% correct intent routing
- Never return cached error or failure response

### Format

- OpenAI-compatible JSON structure
- Include `provider`, `model`, `latency_ms`, `cost` in metadata
- Streaming chunks: valid UTF-8, no mid-token splits
- Tool calling: valid JSON schema, no hallucinated parameters

## System Quality

### Reliability

- Fallback chain must always produce a response
- Never return "No backends available" without remediation steps
- Telemetry must record every request (even failures)
- Cache must not crash on dimension mismatch

### Cost Transparency

- Every response includes actual cost
- Every response includes frontier-equivalent cost
- Savings calculation: frontier_cost - actual_cost
- No hidden charges or undisclosed cloud usage

### Privacy

- Local inference (engine + Ollama): zero data leaves machine
- Cloud fallback: minimal data sent, no logs retained by intermediaries
- API keys: never logged, never exposed
- Telemetry: local SQLite only, user-controlled retention

## CLI Quality

### Output Format

- `efficient status`: Clear backend list, green/yellow/red health
- `efficient report`: Human-readable impact summary
- `efficient bench`: Comparable engine vs pipeline metrics
- Error messages: Actionable remediation steps

### Setup Experience

- `efficient setup`: Auto-detect GPU, Ollama, API keys
- Suggest models based on detected VRAM
- Warn if no backends available
- One-command start for typical workflows

## Quality Checklist

Before any release:

- [ ] All 204 tests pass
- [ ] Benchmark shows engine handles >80% of queries
- [ ] Cache hit rate >20% on warm dataset
- [ ] Cloud fallback <10% on standard tasks
- [ ] x402 payment flow verifies correctly
- [ ] Telemetry records accurately match actual usage
- [ ] No internal kwargs leak to cloud APIs
