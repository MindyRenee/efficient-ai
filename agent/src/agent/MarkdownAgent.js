const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');
const cron = require('node-cron');
const logger = require('../config/logger');
const config = require('../config/config');

/**
 * MarkdownAgent — Autonomous AI business agent.
 *
 * Uses Efficient AI for inference. Reads brain Markdown files for strategy,
 * decides what to do each cycle, executes business actions (scan for gigs,
 * create content, build reputation, track leads), and logs everything to
 * memory files.
 */
class MarkdownAgent {
  constructor() {
    this.brainDir = config.get('storage.brain_dir');
    this.memoryDir = config.get('storage.memory_dir');
    this.efficientHost = config.get('efficient.host');
    this.isRunning = false;
    this.currentCycle = null;
    this.cycleLock = null;
    this.ensureDirectories();
  }

  ensureDirectories() {
    [this.brainDir, this.memoryDir].forEach(dir => {
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    });
  }

  parseMarkdown(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/);
      if (match) {
        const metadata = yaml.load(match[1], { schema: yaml.FAILSAFE_SCHEMA });
        return { metadata: metadata || {}, content: match[2].trim() };
      }
      return { metadata: {}, content: content.trim() };
    } catch (e) {
      return { metadata: {}, content: '' };
    }
  }

  loadBrain() {
    const brain = {};
    if (!fs.existsSync(this.brainDir)) return brain;
    const files = fs.readdirSync(this.brainDir).filter(f => f.endsWith('.md'));
    files.forEach(f => { brain[f.replace('.md', '')] = this.parseMarkdown(path.join(this.brainDir, f)); });
    return brain;
  }

  loadMemory() {
    const memory = {};
    if (!fs.existsSync(this.memoryDir)) return memory;
    const files = fs.readdirSync(this.memoryDir).filter(f => f.endsWith('.md'));
    files.forEach(f => { memory[f.replace('.md', '')] = this.parseMarkdown(path.join(this.memoryDir, f)); });
    return memory;
  }

  async updateMemory(key, content, mode = 'overwrite') {
    const filePath = path.join(this.memoryDir, `${key}.md`);
    try {
      if (mode === 'append') {
        const existing = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
        const maxSize = config.get('storage.max_log_size_mb') * 1024 * 1024;
        const combined = existing + '\n' + content;
        const trimmed = combined.length > maxSize ? combined.slice(-maxSize) : combined;
        fs.writeFileSync(filePath, trimmed);
      } else {
        fs.writeFileSync(filePath, content);
      }
    } catch (e) {
      logger.error(`Failed to update memory file ${key}`, { error: e.message });
    }
  }

  /** Build system prompt from brain files */
  buildSystemPrompt(brain) {
    const parts = [];
    if (brain.goals) parts.push(`## Goals\n${brain.goals.content}`);
    if (brain.skills) parts.push(`## Capabilities\n${brain.skills.content}`);
    if (brain.strategy_weights) parts.push(`## Strategy\n${brain.strategy_weights.content}`);
    if (brain.guardrails) parts.push(`## Guardrails\n${brain.guardrails.content}`);
    if (brain.the_loop) parts.push(`## Operating Cycle\n${brain.the_loop.content}`);
    return parts.join('\n\n');
  }

  /** Call Efficient AI local server with retry */
  async chat(messages, opts = {}) {
    const maxRetries = opts.retries ?? 3;
    let lastError;

    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 30000);
        const res = await fetch(`${this.efficientHost}/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: 'auto',
            messages,
            stream: false,
            temperature: opts.temperature ?? 0.7,
            max_tokens: opts.max_tokens ?? 1024,
          }),
          signal: controller.signal,
        });
        clearTimeout(timeout);

        if (res.status >= 500) {
          const text = await res.text();
          lastError = new Error(`Efficient AI error ${res.status}: ${text}`);
          logger.warn(`Chat attempt ${attempt + 1} failed, retrying`, { status: res.status });
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
          continue;
        }

        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Efficient AI error ${res.status}: ${text}`);
        }

        const data = await res.json();
        const choice = data.choices?.[0]?.message;
        const efficient = data._efficient || {};

        return {
          content: choice?.content || '',
          provider: efficient.provider || 'unknown',
          model: efficient.model || 'unknown',
          latency_ms: efficient.latency_ms || 0,
          cost: efficient.cost || 0,
          savings: efficient.savings || 0,
          cache_hit: efficient.cache_hit || false,
          intent: efficient.intent || 'unknown',
          complexity: efficient.complexity || 'unknown',
          raw: data,
        };
      } catch (e) {
        if (e.name === 'AbortError') {
          lastError = new Error('Efficient AI request timed out');
        } else {
          lastError = e;
        }
        if (attempt < maxRetries - 1) {
          logger.warn(`Chat attempt ${attempt + 1} failed, retrying`, { error: lastError.message });
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        }
      }
    }
    throw lastError;
  }

  async runCycle() {
    if (this.currentCycle) { logger.warn('Cycle already running'); return; }
    this.currentCycle = true;
    const cycleId = Date.now();

    try {
      logger.info('Agent cycle started', { cycleId });
      const brain = this.loadBrain();
      const systemPrompt = this.buildSystemPrompt(brain);

      const decision = await this.inferDecision(systemPrompt, brain);
      logger.info('Decision inferred', { decision });

      await this.executeWithEfficientAI(decision, systemPrompt, brain);

      await this.updateMemory('state', this.generateStateYAML(decision));
      await this.updateMemory('daily-log', this.generateLogEntry(decision), 'append');

      logger.info('Agent cycle completed', { cycleId });
    } catch (error) {
      logger.error('Agent cycle failed', { cycleId, error: error.message });
      await this.updateMemory('lessons', this.generateLessonYAML(error), 'append');
    } finally {
      this.currentCycle = false;
    }
  }

  /** Extract JSON from LLM response (handles markdown code fences and surrounding text) */
  extractJSON(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch { /* not pure JSON, try fenced */ }
    const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    if (fenceMatch) {
      try { return JSON.parse(fenceMatch[1].trim()); } catch { /* fenced JSON invalid, try embedded */ }
    }
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      try { return JSON.parse(jsonMatch[0]); } catch { /* no valid JSON found */ }
    }
    return null;
  }

  /** Ask Efficient AI what the agent should do next */
  async inferDecision(systemPrompt, brain) {
    const waterfall = brain.decision_waterfall?.content || '';
    const memory = this.loadMemory();
    const recentLog = memory['daily-log']?.content?.slice(-2000) || '';
    const earnings = memory['earnings']?.metadata || { total: 0 };
    const leads = memory['leads']?.metadata || { leads: [] };
    const opportunities = memory['opportunities']?.metadata || { opportunities: [] };

    const messages = [
      { role: 'system', content: `${systemPrompt}\n\n## Decision Waterfall\n${waterfall}` },
      { role: 'user', content: `Current state:\n- Total earnings: $${earnings.total || 0}\n- Active leads: ${Array.isArray(leads.leads) ? leads.leads.length : 0}\n- Open opportunities: ${Array.isArray(opportunities.opportunities) ? opportunities.opportunities.length : 0}\n\nRecent activity:\n${recentLog}\n\nWhat should I do next to grow revenue? Choose from: scan_gigs, create_content, build_reputation, track_leads, reflect.\n\nRespond with ONLY a JSON object, no other text:\n{"action": "scan_gigs|create_content|build_reputation|track_leads|reflect", "priority": "high|medium|low", "reasoning": "one sentence why"}` }
    ];

    const response = await this.chat(messages, { temperature: 0.3, retries: 3 });
    let decision = this.extractJSON(response.content);
    if (!decision) {
      decision = { action: 'scan_gigs', priority: 'high', reasoning: 'JSON parse failed, defaulting to highest-impact action' };
    }

    decision._routing = {
      provider: response.provider,
      model: response.model,
      latency_ms: response.latency_ms,
      cost: response.cost,
      savings: response.savings,
      cache_hit: response.cache_hit,
      intent: response.intent,
      complexity: response.complexity,
    };

    return decision;
  }

  /** Execute the inferred decision using Efficient AI */
  async executeWithEfficientAI(decision, systemPrompt, _brain) {
    const actionHandlers = {
      scan_gigs: async () => {
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Generate 3 realistic freelance gig opportunities for an AI infrastructure consultant. For each, provide: title, platform (Reddit/Upwork/HackerNews), estimated_budget, and a 2-sentence pitch angle. Format as JSON array: [{"title":"...","platform":"...","budget":"...","pitch":"..."}]` }
        ], { temperature: 0.5, retries: 2 });
        const gigs = this.extractJSON(res.content) || [];
        await this.updateMemory('opportunities', this.generateOpportunitiesYAML(gigs));
        return { type: 'scan_gigs', output: res.content, gigs, ...res };
      },
      create_content: async () => {
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Write a short technical blog post (300 words) about building cost-efficient AI pipelines with local-first inference. Include a title and 3 key takeaways. This should be publishable as-is.` }
        ], { temperature: 0.7, retries: 2 });
        await this.updateMemory('content-log', this.generateContentLogYAML(res.content), 'append');
        return { type: 'content', output: res.content, ...res };
      },
      build_reputation: async () => {
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Write 2 helpful Reddit comments for r/MachineLearning or r/LocalLLaMA that demonstrate expertise in local AI inference. Each comment should be 100-150 words, technically specific, and naturally mention cost savings from local-first inference. Format as JSON array: [{"subreddit":"...","comment":"..."}]` }
        ], { temperature: 0.6, retries: 2 });
        const comments = this.extractJSON(res.content) || [];
        return { type: 'reputation', output: res.content, comments, ...res };
      },
      track_leads: async () => {
        const memory = this.loadMemory();
        const opps = memory['opportunities']?.metadata?.opportunities || [];
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Given these opportunities: ${JSON.stringify(opps)}. Score each lead 1-10 by likelihood to convert and suggest a follow-up action for each. Format as JSON array: [{"title":"...","score":8,"follow_up":"..."}]` }
        ], { temperature: 0.4, retries: 2 });
        const scored = this.extractJSON(res.content) || [];
        await this.updateMemory('leads', this.generateLeadsYAML(scored));
        return { type: 'track_leads', output: res.content, scored, ...res };
      },
      reflect: async () => {
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Reflect on our current business strategy. What's working? What's not? What should we change? Be specific and actionable. Keep it under 200 words.` }
        ], { retries: 2 });
        return { type: 'reflection', output: res.content, ...res };
      },
      default: async () => {
        const res = await this.chat([
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `Execute the action "${decision.action}" with priority "${decision.priority}". Provide a brief status update.` }
        ], { retries: 2 });
        return { type: 'generic', output: res.content, ...res };
      }
    };

    const handler = actionHandlers[decision.action] || actionHandlers.default;
    const result = await handler();

    await this.updateMemory('telemetry', this.generateTelemetryYAML(decision, result), 'append');

    if (result.type === 'scan_gigs' || result.type === 'track_leads') {
      await this.updateMemory('experiments', this.generateExperimentYAML(decision, result), 'append');
    }
  }

  generateStateYAML(decision) {
    return `---
phase: active
last_action: ${decision.action}
last_priority: ${decision.priority}
last_reasoning: "${(decision.reasoning || '').replace(/"/g, '\\"')}"
last_provider: ${decision._routing?.provider || 'unknown'}
last_model: ${decision._routing?.model || 'unknown'}
last_cost: ${decision._routing?.cost || 0}
last_savings: ${decision._routing?.savings || 0}
cache_hit: ${decision._routing?.cache_hit || false}
last_updated: ${new Date().toISOString()}
---

# Agent State

Current agent state
`;
  }

  generateLogEntry(decision) {
    return `---
timestamp: ${new Date().toISOString()}
action: ${decision.action}
priority: ${decision.priority}
provider: ${decision._routing?.provider || 'unknown'}
model: ${decision._routing?.model || 'unknown'}
latency_ms: ${decision._routing?.latency_ms || 0}
cost: ${decision._routing?.cost || 0}
savings: ${decision._routing?.savings || 0}
cache_hit: ${decision._routing?.cache_hit || false}
---
${decision.reasoning || 'No reasoning provided'}
`;
  }

  generateTelemetryYAML(decision, result) {
    return `---
timestamp: ${new Date().toISOString()}
action: ${decision.action}
priority: ${decision.priority}
intent: ${result.intent || 'unknown'}
complexity: ${result.complexity || 'unknown'}
provider: ${result.provider || 'unknown'}
model: ${result.model || 'unknown'}
latency_ms: ${result.latency_ms || 0}
cost: ${result.cost || 0}
savings: ${result.savings || 0}
cache_hit: ${result.cache_hit || false}
---
${result.output || 'No output'}
`;
  }

  generateExperimentYAML(decision, result) {
    return `---
timestamp: ${new Date().toISOString()}
action: ${decision.action}
status: proposed
hypothesis: "${(result.output || '').slice(0, 200).replace(/"/g, '\\"')}"
provider: ${result.provider || 'unknown'}
model: ${result.model || 'unknown'}
---
Proposed experiment from agent cycle
`;
  }

  generateOpportunitiesYAML(gigs) {
    const opps = (gigs || []).map(g => `- title: "${(g.title || '').replace(/"/g, '\\"')}"\n  platform: ${g.platform || 'unknown'}\n  budget: "${g.budget || 'unknown'}"\n  pitch: "${(g.pitch || '').replace(/"/g, '\\"')}"`).join('\n');
    return `---
opportunities:
${opps || '[]'}
last_updated: ${new Date().toISOString()}
---

# Opportunities

Scanned freelance gig opportunities
`;
  }

  generateLeadsYAML(scored) {
    const leads = (scored || []).map(l => `- title: "${(l.title || '').replace(/"/g, '\\"')}"\n  score: ${l.score || 0}\n  follow_up: "${(l.follow_up || '').replace(/"/g, '\\"')}"`).join('\n');
    return `---
leads:
${leads || '[]'}
last_updated: ${new Date().toISOString()}
---

# Leads

Scored and tracked leads
`;
  }

  generateContentLogYAML(content) {
    const titleMatch = content.match(/^#\s+(.+)$/m);
    const title = titleMatch ? titleMatch[1] : 'Untitled';
    return `---
timestamp: ${new Date().toISOString()}
title: "${title.replace(/"/g, '\\"')}"
status: draft
word_count: ${content.split(/\s+/).length}
---
${content}
`;
  }

  generateLessonYAML(error) {
    return `---
timestamp: ${new Date().toISOString()}
error: ${error.message}
---
${error.stack || ''}
`;
  }

  start() {
    const interval = config.get('agent.cycle_interval_minutes');
    logger.info(`Starting Markdown Agent → Efficient AI @ ${this.efficientHost} (every ${interval}m)`);
    this.runCycle().catch(e => logger.error('Initial cycle failed', { error: e.message }));
    this.cycleLock = cron.schedule(`*/${interval} * * * *`, () => this.runCycle().catch(e => logger.error('Scheduled cycle failed', { error: e.message })));
    this.isRunning = true;
  }

  stop() {
    if (this.cycleLock) { this.cycleLock.stop(); this.cycleLock = null; }
    this.isRunning = false;
    logger.info('Markdown Agent stopped');
  }

  getStatus() {
    return {
      running: this.isRunning,
      currentCycle: !!this.currentCycle,
      brainFiles: fs.existsSync(this.brainDir) ? fs.readdirSync(this.brainDir).filter(f => f.endsWith('.md')) : [],
      efficientHost: this.efficientHost,
    };
  }
}

module.exports = MarkdownAgent;
