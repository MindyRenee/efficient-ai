---
name: Emergency Procedures
version: 2.0
---

# Emergency Procedures

What to do when Efficient AI encounters critical failures.

## Emergency Types

### 1. All Backends Down

**Symptoms:**

- Engine cannot handle + Ollama not running + no cloud keys configured
- Every request returns "No inference backends available"
- System is effectively offline

**Actions:**

1. Check Ollama status: `ollama list`
2. If Ollama down: start with `ollama serve`
3. If no models: `ollama pull qwen2.5:7b`
4. If no cloud keys: set OPENAI_API_KEY or GROQ_API_KEY
5. Verify with `efficient status`
6. Resume serving

### 2. SQLite Database Corruption

**Symptoms:**

- `sqlite3.OperationalError` on cache or telemetry access
- Cache returns nothing despite entries existing
- Telemetry reports zero requests despite traffic

**Actions:**

1. Stop x402 server if running
2. Rename `~/.efficient/cache.db` to `cache.db.bak`
3. Rename `~/.efficient/telemetry.db` to `telemetry.db.bak`
4. Restart — databases auto-rebuild
5. If telemetry critical, attempt recovery with `sqlite3 .recover`
6. Investigate root cause (disk space? power loss?)

### 3. x402 Payment Failure

**Symptoms:**

- Payments verify but response never delivers
- Double-spend errors in x402 middleware
- Revenue discrepancies between on-chain and telemetry

**Actions:**

1. Stop x402 server immediately
2. Check wallet balance and RPC endpoint health
3. Verify no race condition in payment verification
4. Reconcile on-chain payments with telemetry records
5. Fix bug before restarting
6. Honor any valid payments made during outage

### 4. GPU / OOM Crashes

**Symptoms:**

- Ollama crashes mid-request
- CUDA out-of-memory errors
- System becomes unresponsive

**Actions:**

1. Reduce loaded models: `ollama stop <model>`
2. Lower quantization: pull Q4 instead of Q8
3. Reduce concurrent requests (if proxy server)
4. Fallback to CPU-only Ollama mode temporarily
5. Monitor with `nvidia-smi` or equivalent

### 5. API Key Leak

**Symptoms:**

- Keys visible in logs or error traces
- Unauthorized usage on cloud provider dashboard
- Unexpected cost spikes

**Actions:**

1. Revoke leaked key immediately at provider
2. Generate new key
3. Update environment variable
4. Audit logs for unauthorized usage
5. Review log sanitization code

## Recovery Verification

After any emergency:

- Run `efficient status` to verify all backends
- Run `efficient bench` to validate pipeline
- Check telemetry shows requests being recorded
- Verify cache is storing and retrieving
