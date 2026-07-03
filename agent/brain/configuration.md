---
name: Configuration
version: 2.0
---

# System Configuration

Global settings for Efficient AI.

## Operational Settings

### Routing

- local_first: true
- cache_enabled: true
- telemetry_enabled: true
- similarity_threshold: 0.92
- max_cache_entries: 10000
- cache_ttl_seconds: 0 (infinite)

### API Configuration

- ollama_timeout_ms: 30000
- cloud_timeout_ms: 60000
- max_retries: 1
- fallback_chain: engine → ollama → cloud
- stream_buffer_ms: 10

## Hardware Configuration

### GPU

- auto_detect: true
- vram_required_engine: 0 MB
- vram_required_ollama_7b: 4500 MB
- vram_required_ollama_14b: 9000 MB
- vram_required_ollama_32b: 20000 MB

### Ollama

- host: <http://localhost:11434>
- auto_detect_models: true
- preferred_models:
  - qwen2.5:7b (moderate tasks)
  - qwen2.5:14b (complex tasks)
  - phi3:mini (trivial tasks)
- embedding_model: nomic-embed-text

## Cloud Configuration

### OpenAI

- model: gpt-4o-mini (default), gpt-4o (fallback)
- base_url: <https://api.openai.com/v1>
- key: OPENAI_API_KEY

### Groq

- model: llama-3.3-70b-versatile
- base_url: <https://api.groq.com/openai/v1>
- key: GROQ_API_KEY

### OpenRouter

- model: varies by tier
- base_url: <https://openrouter.ai/api/v1>
- key: OPENROUTER_API_KEY

## x402 Configuration

### Server

- enabled: false
- host: 0.0.0.0
- port: 8000
- network: eip155:8453 (Base mainnet)
- currency: USDC
- wallet: EFFICIENT_WALLET env var

### Pricing

- cache_hit: $0.001
- engine: $0.005
- ollama: $0.01
- cloud_small: $0.05
- cloud_mid: $0.10
- cloud_large: $0.25
- cloud_frontier: $0.50

## Data Paths

- config: ~/.efficient/config.json
- cache: ~/.efficient/cache.db
- telemetry: ~/.efficient/telemetry.db
