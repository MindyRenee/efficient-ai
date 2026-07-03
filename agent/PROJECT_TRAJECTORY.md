# Project Trajectory Guide

## Original Vision

This project is a **simple autonomous AI agent with its entire brain stored in Markdown files**. The agent:

1. Reads 18 brain files (decision logic, strategies, guardrails, personality)
2. Reads 8 memory files (state, earnings, leads, lessons)
3. Makes decisions based on the decision waterfall
4. Executes actions (scan for gigs, create content, publish, track)
5. Updates memory files with results

**The core innovation**: Everything the agent knows and does is human-readable Markdown files. No databases, no complex state management, just .md files.

## What Got Off Trajectory

### Critical Divergences (Should Be Removed)

1. **x402 Payment Protocol**
   - Added blockchain payments for brain file access
   - This is NOT the original goal
   - The agent is supposed to MAKE money via freelance/content, not SELL its brain
   - Remove: `src/middleware/x402.js`, x402 config, x402 routes

2. **Enterprise Security Overkill**
   - JWT authentication, rate limiting, input sanitization
   - These are for production SaaS, not a personal autonomous agent
   - The agent runs locally; you don't need auth to access your own agent's brain
   - Remove: `src/middleware/auth.js`, `src/middleware/validation.js`, `src/middleware/rateLimit.js`

3. **Alpha Strategies Content**
   - Added generic 2026 AI agent monetization advice to brain files
   - This is not specific to THIS agent's actual knowledge/expertise
   - The brain should contain YOUR specific strategies, not generic "alpha" content
   - Remove: `brain/alpha_strategies.md`, revert other brain files to original simple strategies

4. **Complex Configuration**
   - Convict configuration with type validation
   - Overkill for a simple agent
   - Environment variables are sufficient
   - Simplify: Use simple dotenv-based config

5. **Prometheus Metrics & CI/CD**
   - Enterprise monitoring and automated testing
   - Not needed for a personal agent
   - Remove: prom-client, GitHub Actions, Jest tests

### Moderate Divergences (Should Be Simplified)

1. **Structured Logging**
   - Winston with daily rotation is fine, but could be simpler
   - Keep but simplify to basic file logging

2. **Monitor Dashboard**
   - The web interface is useful for visibility
   - Keep but remove authentication requirement

## What Are Genuine Improvements (Should Keep)

1. **File Locking**
   - proper-lockfile prevents concurrent write corruption
   - Essential for reliability
   - Keep

2. **Graceful Shutdown**
   - SIGINT/SIGTERM handling
   - Prevents data loss
   - Keep

3. **Error Handling**
   - Classified error levels with appropriate responses
   - Essential for autonomous operation
   - Keep

4. **Monitor Dashboard**
   - Real-time visibility into agent state
   - Very useful for debugging and monitoring
   - Keep (but remove auth)

5. **Append-Only Logging**
   - daily-log.md preserves full history
   - Essential for learning and debugging
   - Keep

## Correct Trajectory

### Phase 1: Core Agent (Priority 1)
- Simple Node.js process that reads brain/memory .md files
- Decision waterfall logic
- Action execution (scan, create, publish, track)
- Memory file updates
- **No authentication, no payments, no enterprise features**

### Phase 2: Reliability (Priority 2)
- File locking for concurrent writes
- Graceful shutdown
- Error handling and recovery
- Append-only logging
- Basic file logging (not full Winston)

### Phase 3: Visibility (Priority 3)
- Simple monitor dashboard (no auth required)
- Real-time agent status
- Read-only brain/memory file viewing
- Simple HTTP server

### Phase 4: Customization (Priority 4)
- User fills in their actual expertise in brain files
- User configures their actual platforms in integration_points.md
- User sets their actual goals in goals.md
- User defines their actual niche in niche.md

### Phase 5: Monetization (Priority 5 - Original Goal)
- Agent scans Reddit for freelance gigs
- Agent creates content to build reputation
- Agent tracks earnings from actual work
- **NOT** selling brain files to other agents
- **NOT** blockchain payments
- **NOT** generic "alpha strategies"

## Red Flags That Indicate Trajectory Drift

If you find yourself adding any of these, STOP and reconsider:

- ❌ Authentication/authorization systems
- ❌ Payment processing or blockchain integration
- ❌ Rate limiting or API gateway features
- ❌ Enterprise security (CSP, Helmet, CORS)
- ❌ Complex configuration management
- ❌ CI/CD pipelines
- ❌ Testing frameworks (Jest, etc.)
- ❌ Metrics/monitoring beyond basic logging
- ❌ Generic "strategies" not specific to the user
- ❌ Features that require external services to function

## The Litmus Test

Before adding any feature, ask:

1. **Does this help the agent find freelance opportunities?**
2. **Does this help the agent create better content?**
3. **Does this help the agent build reputation?**
4. **Does this help the agent track actual earnings?**

If the answer is NO to all four, the feature is off trajectory.

## Example: Good vs Bad Additions

### Good Additions (On Trajectory)
- Add a new platform to scan for gigs (e.g., Upwork)
- Improve content quality by adding better templates
- Add better lead scoring logic
- Improve error recovery for failed API calls
- Add a new brain file for a specific domain expertise

### Bad Additions (Off Trajectory)
- Add authentication to protect brain files
- Add blockchain payments to sell brain access
- Add rate limiting to prevent API abuse
- Add Prometheus metrics for monitoring
- Add generic "alpha strategies" from web research
- Add CI/CD pipeline for automated testing

## Summary

**The Goal**: A simple, reliable autonomous agent that makes money via freelance work and content creation, with its entire brain in human-readable Markdown files.

**The Trajectory**: Core agent → Reliability → Visibility → Customization → Actual monetization (freelance/content)

**The Anti-Pattern**: Enterprise features, authentication, payments, generic strategies, complexity for complexity's sake.

**Remember**: The innovation is the Markdown-based brain, not the enterprise infrastructure around it. Keep it simple.
