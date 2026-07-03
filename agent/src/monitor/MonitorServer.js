const express = require('express');
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');
const logger = require('../config/logger');
const config = require('../config/config');
const { validateFileName } = require('../middleware/validation');
const { sanitizeInput, errorHandler, notFoundHandler } = require('../middleware/security');
const promClient = require('prom-client');

const register = new promClient.Registry();

const httpRequestDuration = new promClient.Histogram({
  name: 'http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status_code'],
  registers: [register]
});

const httpRequestsTotal = new promClient.Counter({
  name: 'http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'route', 'status_code'],
  registers: [register]
});

class MonitorServer {
  constructor(agent) {
    this.app = express();
    this.agent = agent;
    this.port = config.get('monitor.port');
    this.brainDir = config.get('storage.brain_dir');
    this.memoryDir = config.get('storage.memory_dir');
    this.setupMiddleware();
    this.setupRoutes();
  }

  setupMiddleware() {
    this.app.use(express.json());
    this.app.use(sanitizeInput);
    
    this.app.use((req, res, next) => {
      const start = Date.now();
      res.on('finish', () => {
        const duration = (Date.now() - start) / 1000;
        httpRequestDuration.observe(
          { method: req.method, route: req.path, status_code: res.statusCode },
          duration
        );
        httpRequestsTotal.inc(
          { method: req.method, route: req.path, status_code: res.statusCode }
        );
      });
      next();
    });
  }

  setupRoutes() {
    this.app.get('/health', this.healthCheck.bind(this));
    this.app.get('/metrics', this.metrics.bind(this));
    
    this.app.get('/api/status', this.getStatus.bind(this));
    this.app.get('/api/brain', this.listBrainFiles.bind(this));
    this.app.get('/api/brain/:file', validateFileName, this.getBrainFile.bind(this));
    this.app.get('/api/memory', this.listMemoryFiles.bind(this));
    this.app.get('/api/memory/:file', validateFileName, this.getMemoryFile.bind(this));
    this.app.get('/api/efficient/status', this.getEfficientStatus.bind(this));
    this.app.get('/api/efficient/telemetry', this.getEfficientTelemetry.bind(this));
    this.app.use(express.static(path.join(__dirname, '../../public')));
    
    this.app.use(notFoundHandler);
    this.app.use(errorHandler);
  }

  healthCheck(req, res) {
    const health = {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      agent: this.agent.getStatus()
    };
    
    res.json(health);
  }

  metrics(req, res) {
    res.set('Content-Type', register.contentType);
    res.end(register.metrics());
  }

  getStatus(req, res) {
    try {
      const brainFiles = fs.readdirSync(this.brainDir).filter(f => f.endsWith('.md'));
      const memoryFiles = fs.existsSync(this.memoryDir) 
        ? fs.readdirSync(this.memoryDir).filter(f => f.endsWith('.md')) 
        : [];
      
      const state = fs.existsSync(path.join(this.memoryDir, 'state.md')) 
        ? this.parseMarkdown(path.join(this.memoryDir, 'state.md')).metadata 
        : { phase: 'not_started' };
      
      res.json({
        brain_files: brainFiles.length,
        memory_files: memoryFiles.length,
        current_state: state,
        agent_running: this.agent.getStatus().running,
        agent_status: this.agent.getStatus()
      });
    } catch (error) {
      logger.error('Failed to get status', { error: error.message });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  getBrainFile(req, res) {
    try {
      const filePath = path.join(this.brainDir, `${req.params.file}.md`);
      
      if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
      }
      
      const data = this.parseMarkdown(filePath);
      res.json(data);
    } catch (error) {
      logger.error('Failed to get brain file', { 
        file: req.params.file,
        error: error.message 
      });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  getMemoryFile(req, res) {
    try {
      const filePath = path.join(this.memoryDir, `${req.params.file}.md`);
      
      if (!fs.existsSync(filePath)) {
        return res.status(404).json({ error: 'File not found' });
      }
      
      const data = this.parseMarkdown(filePath);
      res.json(data);
    } catch (error) {
      logger.error('Failed to get memory file', { 
        file: req.params.file,
        error: error.message 
      });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  listBrainFiles(req, res) {
    try {
      const files = fs.readdirSync(this.brainDir).filter(f => f.endsWith('.md'));
      const fileData = files.map(file => {
        const data = this.parseMarkdown(path.join(this.brainDir, file));
        return {
          name: file.replace('.md', ''),
          metadata: data.metadata
        };
      });
      res.json(fileData);
    } catch (error) {
      logger.error('Failed to list brain files', { error: error.message });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  listMemoryFiles(req, res) {
    try {
      if (!fs.existsSync(this.memoryDir)) {
        return res.json([]);
      }
      
      const files = fs.readdirSync(this.memoryDir).filter(f => f.endsWith('.md'));
      const fileData = files.map(file => {
        const data = this.parseMarkdown(path.join(this.memoryDir, file));
        return {
          name: file.replace('.md', ''),
          metadata: data.metadata
        };
      });
      res.json(fileData);
    } catch (error) {
      logger.error('Failed to list memory files', { error: error.message });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  async getEfficientStatus(req, res) {
    const efficientHost = config.get('efficient.host');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const response = await fetch(`${efficientHost}/v1/models`, { method: 'GET', signal: controller.signal });
      clearTimeout(timeout);
      res.json({ connected: response.ok, host: efficientHost, status: response.status });
    } catch (error) {
      clearTimeout(timeout);
      res.json({ connected: false, host: efficientHost, error: error.message });
    }
  }

  getEfficientTelemetry(req, res) {
    try {
      const telemetryPath = path.join(this.memoryDir, 'telemetry.md');
      if (!fs.existsSync(telemetryPath)) {
        return res.json({ entries: [] });
      }
      const data = fs.readFileSync(telemetryPath, 'utf8');
      const entries = [];
      const blocks = data.split(/\n---\r?\n/);
      for (const block of blocks) {
        const lines = block.trim().split(/\r?\n/);
        const meta = {};
        let inMeta = false;
        for (const line of lines) {
          if (line.startsWith('timestamp:')) { meta.timestamp = line.substring(line.indexOf(': ') + 2); inMeta = true; }
          if (line.startsWith('provider:')) meta.provider = line.substring(line.indexOf(': ') + 2);
          if (line.startsWith('model:')) meta.model = line.substring(line.indexOf(': ') + 2);
          if (line.startsWith('cost:')) meta.cost = parseFloat(line.substring(line.indexOf(': ') + 2));
          if (line.startsWith('savings:')) meta.savings = parseFloat(line.substring(line.indexOf(': ') + 2));
          if (line.startsWith('cache_hit:')) meta.cache_hit = line.substring(line.indexOf(': ') + 2) === 'true';
        }
        if (inMeta) entries.push(meta);
      }
      res.json({ entries: entries.slice(-50) });
    } catch (error) {
      logger.error('Failed to read telemetry', { error: error.message });
      res.status(500).json({ error: 'Internal server error' });
    }
  }

  parseMarkdown(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf8');
      const frontmatterRegex = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/;
      const match = content.match(frontmatterRegex);
      
      if (match) {
        const metadata = yaml.load(match[1], { schema: yaml.FAILSAFE_SCHEMA });
        return {
          metadata: metadata || {},
          content: match[2]
        };
      }
      
      return { metadata: {}, content };
    } catch (error) {
      logger.error('Failed to parse markdown', { 
        filePath, 
        error: error.message 
      });
      return { metadata: {}, content: '' };
    }
  }

  start() {
    this.server = this.app.listen(this.port, () => {
      logger.info(`Monitor server running on port ${this.port}`);
      logger.info(`Dashboard: http://localhost:${this.port}`);
      logger.info(`Health check: http://localhost:${this.port}/health`);
      logger.info(`Metrics: http://localhost:${this.port}/metrics`);
    });
  }

  stop() {
    if (this.server) {
      this.server.close();
      logger.info('Monitor server stopped');
    }
  }
}

module.exports = MonitorServer;
