---
name: Error Handling
---

# Error Handling Strategy

How Efficient AI handles failures.

## Error Classification

### Level 1: Backend Failure (Auto-Fallback)

- Engine cannot handle intent/complexity
- Ollama not running or model not loaded
- Cloud API rate limit or timeout
- Network transient error

**Action**: Route to next backend in chain (engine → ollama → cloud). Log fallback in telemetry.

### Level 2: Degraded Performance (Log and Continue)

- Cache miss on expected hit
- Slower-than-normal Ollama response
- Embedding dimension mismatch (cache skip)
- Telemetry queue full (drop oldest)

**Action**: Log to stderr, continue serving request. No user-facing error.

### Level 3: Configuration Error (Alert)

- No inference backends available
- Invalid API key
- Missing required model for tier
- Corrupted SQLite database

**Action**: Return clear error message to user with remediation steps. Log to telemetry.

### Level 4: Emergency (Stop and Alert)

- x402 payment verification failure (double-spend)
- SQLite WAL corruption (both cache and telemetry)
- Security breach (unauthorized proxy access)

**Action**: Stop x402 server. Alert admin via configured channel. Preserve audit trail.

## Fallback Chain

Engine cannot handle → Ollama fallback → Cloud fallback → Error
   (0ms)                (50-500ms)       (500-2000ms)    (rare)

- Each fallback is transparent to user
- Response includes actual provider used
- Telemetry tracks fallback frequency per backend

## Recovery Procedures

### Cache Database Corruption

1. Detect: `sqlite3.OperationalError` on cache access
2. Action: Disable cache, serve requests uncached
3. Recovery: Delete `~/.efficient/cache.db`, rebuild on next startup
4. Log: Record corruption event in telemetry

### Ollama Failure

1. Detect: HTTP timeout or connection refused on `localhost:11434`
2. Action: Mark Ollama unavailable in config, route to cloud
3. Recovery: Poll Ollama health every 30s, re-enable when back
4. Log: Record downtime in telemetry

### Cloud API Key Invalid

1. Detect: 401/403 from provider
2. Action: Skip that provider, try next in `available_providers`
3. Recovery: Alert admin to update key in `.env`
4. Log: Record auth failure per provider

### Telemetry Queue Overflow

1. Detect: In-memory queue > 1000 records
2. Action: Drop oldest 10% of records
3. Recovery: Increase flush frequency temporarily
4. Log: Record overflow event
