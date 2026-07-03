# Markdown Agent — Efficient AI Integration

An autonomous AI agent powered by [Efficient AI](https://github.com/efficient-ai/efficient-ai) for inference. The agent's brain lives in 15 Markdown files. All inference is routed through Efficient AI's local-first pipeline: embedded deterministic engine → Ollama local LLMs → cloud fallback, with semantic caching, intent classification, and x402 micropayments.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────────────────┐
│   Markdown Agent    │     │        Efficient AI Server        │
│                     │     │                                  │
│  brain/*.md (15)    │     │  ┌──────────┐  ┌──────────────┐  │
│  memory/*.md (9)    │────▶│  │ Semantic │  │   Embedded   │  │
│  MarkdownAgent.js   │     │  │  Cache   │  │   Engine     │  │
│  Monitor Dashboard  │     │  └──────────┘  └──────────────┘  │
│                     │     │       │              │            │
│  Cycle:             │     │  ┌──────────┐  ┌──────────────┐  │
│  1. Load brain      │     │  │  Intent  │  │   Ollama     │  │
│  2. Build prompt    │     │  │ Router   │  │   (local)    │  │
│  3. Infer decision  │     │  └──────────┘  └──────────────┘  │
│  4. Execute action  │     │       │              │            │
│  5. Log telemetry   │     │  ┌──────────┐  ┌──────────────┐  │
│  6. Update memory   │     │  │ x402     │  │   Cloud      │  │
│                     │     │  │ Payments │  │  Fallback    │  │
└─────────────────────┘     │  └──────────┘  └──────────────┘  │
                            │  ┌──────────┐                     │
                            │  │Telemetry │                     │
                            │  └──────────┘                     │
                            └──────────────────────────────────┘
```

## Enterprise Features

### Efficient AI Inference Pipeline

- **Embedded Engine** — Deterministic algorithms handle 80% of queries at $0, <1ms
- **Semantic Caching** — SQLite + embedding similarity avoids recomputing similar queries
- **Intent Classification** — Routes by intent and complexity to the optimal backend
- **Local Ollama** — Runs local LLMs (phi3:mini, qwen2.5:7b, llama3.1:8b) for $0/token
- **Cloud Fallback** — Uses GPT-4o/Groq only for the hardest 5% of queries
- **x402 Micropayments** — Per-request USDC payments on Base (eip155:8453)

### Security

- **JWT Authentication** — Token-based auth for API access
- **Rate Limiting** — Configurable limits to prevent abuse
- **Input Validation** — Joi-based validation for all inputs
- **Helmet.js** — Security headers and CSP
- **Path Traversal Protection** — Validated file access

### Observability

- **Structured Logging** — Winston with daily rotation
- **Prometheus Metrics** — HTTP request duration and counters
- **Telemetry Dashboard** — Real-time routing decisions, cost, savings, cache hits
- **Health Checks** — `/health` endpoint for monitoring

### Reliability

- **File Locking** — proper-lockfile for concurrent write protection
- **Graceful Shutdown** — SIGINT/SIGTERM handling
- **Error Handling** — Comprehensive error handling with lesson logging
- **Concurrency Control** — Prevents overlapping agent cycles

## How It Works

1. **Brain Files** (`brain/*.md`) — 15 Markdown files defining the agent's goals, strategies, guardrails, decision waterfall, and operational knowledge
2. **Memory Files** (`memory/*.md`) — 9 Markdown files tracking state, daily logs, telemetry, experiments, and lessons
3. **Agent Engine** (`MarkdownAgent.js`) — Node.js process that:
   - Loads brain files and builds a system prompt
   - Calls Efficient AI's `/v1/chat/completions` to infer next action
   - Executes the action via another inference call
   - Logs routing metadata (provider, model, cost, savings, cache hit) to memory
4. **Monitor Dashboard** (`monitor.js`) — Web interface showing agent status, brain/memory files, and Efficient AI telemetry

## File Structure

```
markdown-agent/
├── agent.js              # Main agent entry point
├── monitor.js            # Monitoring dashboard entry point
├── package.json
├── .env.example
├── .markdownlint.json    # Lint config
├── brain/                # Agent's brain (15 files)
│   ├── the_loop.md
│   ├── decision_waterfall.md
│   ├── alpha_strategies.md
│   ├── guardrails.md
│   ├── strategy_weights.md
│   ├── goals.md
│   ├── skills.md
│   ├── integration_points.md
│   ├── configuration.md
│   ├── error_handling.md
│   ├── emergency_procedures.md
│   ├── experiment_framework.md
│   ├── quality_standards.md
│   ├── performance_metrics.md
│   ├── learning_system.md
│   └── ...
├── memory/               # Agent's memory (9 files)
│   ├── state.md
│   ├── daily-log.md
│   ├── telemetry.md
│   ├── experiments.md
│   ├── lessons.md
│   ├── opportunities.md
│   ├── leads.md
│   ├── earnings.md
│   └── content-log.md
└── public/
    └── index.html        # Dashboard UI
```

## Setup

### Prerequisites

1. **Efficient AI** — Install and configure the Efficient AI backend:
```bash
cd efficient-ai
pip install -e .
efficient setup
efficient serve --port 8000
```

2. **Ollama** (optional but recommended) — Install from [ollama.com](https://ollama.com), then pull models:
```bash
ollama pull phi3:mini
ollama pull qwen2.5:7b
```

### Agent Setup

1. Install dependencies:
```bash
cd markdown-agent
npm install
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Set `EFFICIENT_HOST` to your Efficient AI server URL (default: `http://localhost:8000`)

4. Start the agent:
```bash
npm start
```

5. Start the monitor (in another terminal):
```bash
npm run monitor
```

6. Visit the dashboard at `http://localhost:3001`

## API Endpoints

### Public

- `GET /health` — Health check
- `GET /metrics` — Prometheus metrics
- `GET /api/brain` — List all brain files

### Efficient AI

- `GET /api/efficient/status` — Check Efficient AI server connection
- `GET /api/efficient/telemetry` — Recent routing telemetry entries

### Protected (requires JWT)

- `POST /api/auth/login` — Login and get JWT token
- `GET /api/status` — Get agent status
- `GET /api/brain/:file` — Get specific brain file (JWT OR x402 payment)
- `GET /api/memory` — List all memory files
- `GET /api/memory/:file` — Get specific memory file

## The 15 Brain Files

### Core Logic

- **the_loop.md** — The Efficient AI inference pipeline cycle
- **decision_waterfall.md** — Priority order for routing and optimization decisions
- **guardrails.md** — System integrity and secure operation rules

### Strategy

- **alpha_strategies.md** — Cache pre-warming, intent bypass, dynamic pricing
- **strategy_weights.md** — Backend priority weights (cache → engine → Ollama → cloud)

### Operations

- **error_handling.md** — Backend failure, degraded performance, recovery procedures
- **experiment_framework.md** — Cache optimization, classification accuracy, engine coverage
- **quality_standards.md** — Response latency, accuracy, cost transparency

### System

- **goals.md** — Cost elimination, speed, revenue via x402, local-first adoption
- **skills.md** — Efficient AI capabilities (engine, Ollama, cloud, router, x402)
- **integration_points.md** — Core backends, data stores, payment integration
- **configuration.md** — Routing, API, hardware, cloud, x402, data paths
- **emergency_procedures.md** — Backend outages, DB corruption, payment failures
- **performance_metrics.md** — Cost, speed, revenue, system health metrics
- **learning_system.md** — Engine failure patterns, cache miss analysis, classification errors

## The 9 Memory Files

- **state.md** — Current agent state (phase, last action, routing metadata)
- **daily-log.md** — Append-only journal of all actions with routing info
- **telemetry.md** — Per-request routing decisions (provider, model, cost, savings, cache)
- **experiments.md** — Proposed experiments from agent cycles
- **lessons.md** — Errors and insights from failed cycles
- **opportunities.md** — Found opportunities
- **leads.md** — Evaluated leads
- **earnings.md** — Revenue tracking
- **content-log.md** — Content created by the agent

## Dashboard

The dashboard at `http://localhost:3001` shows:

- **Agent Status** — Running state, current phase, last action
- **Efficient AI** — Connection status, last provider, cost, total savings, cache hit rate
- **Brain Files** — Browse all 15 brain files
- **Memory Files** — Browse all 9 memory files
- **Telemetry Tab** — Per-request routing table (time, provider, model, cost, savings, cache)
- Auto-refreshes every 30 seconds

## License

MIT
