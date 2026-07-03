const MarkdownAgent = require('../../src/agent/MarkdownAgent');
const fs = require('fs');
const path = require('path');

describe('MarkdownAgent', () => {
  let agent;
  const testBrainDir = path.join(__dirname, '../test-data/brain');
  const testMemoryDir = path.join(__dirname, '../test-data/memory');

  beforeEach(() => {
    if (!fs.existsSync(testBrainDir)) {
      fs.mkdirSync(testBrainDir, { recursive: true });
    }
    if (!fs.existsSync(testMemoryDir)) {
      fs.mkdirSync(testMemoryDir, { recursive: true });
    }
    
    agent = new MarkdownAgent();
    agent.brainDir = testBrainDir;
    agent.memoryDir = testMemoryDir;
  });

  afterEach(() => {
    if (fs.existsSync(testBrainDir)) {
      fs.rmSync(testBrainDir, { recursive: true });
    }
    if (fs.existsSync(testMemoryDir)) {
      fs.rmSync(testMemoryDir, { recursive: true });
    }
  });

  describe('parseMarkdown', () => {
    it('should parse markdown with YAML frontmatter', () => {
      const testFile = path.join(testBrainDir, 'test.md');
      fs.writeFileSync(testFile, '---\ntest: value\n---\nContent here');
      
      const result = agent.parseMarkdown(testFile);
      
      expect(result.metadata).toEqual({ test: 'value' });
      expect(result.content).toBe('Content here');
    });

    it('should handle markdown without frontmatter', () => {
      const testFile = path.join(testBrainDir, 'test.md');
      fs.writeFileSync(testFile, 'Just content');
      
      const result = agent.parseMarkdown(testFile);
      
      expect(result.metadata).toEqual({});
      expect(result.content).toBe('Just content');
    });

    it('should handle parsing errors gracefully', () => {
      const result = agent.parseMarkdown('/nonexistent/file.md');
      
      expect(result.metadata).toEqual({});
      expect(result.content).toBe('');
    });
  });

  describe('loadBrain', () => {
    it('should load all markdown files from brain directory', () => {
      fs.writeFileSync(path.join(testBrainDir, 'file1.md'), '---\ntest: 1\n---\nContent');
      fs.writeFileSync(path.join(testBrainDir, 'file2.md'), '---\ntest: 2\n---\nContent');
      
      const brain = agent.loadBrain();
      
      expect(Object.keys(brain)).toContain('file1');
      expect(Object.keys(brain)).toContain('file2');
    });
  });

  describe('loadMemory', () => {
    it('should load all markdown files from memory directory', () => {
      fs.writeFileSync(path.join(testMemoryDir, 'state.md'), '---\nphase: idle\n---\nContent');
      
      const memory = agent.loadMemory();
      
      expect(Object.keys(memory)).toContain('state');
      expect(memory.state.metadata.phase).toBe('idle');
    });
  });

  describe('updateMemory', () => {
    it('should overwrite memory file', async () => {
      await agent.updateMemory('test', 'new content');
      
      const content = fs.readFileSync(path.join(testMemoryDir, 'test.md'), 'utf8');
      expect(content).toBe('new content');
    });

    it('should append to memory file', async () => {
      await agent.updateMemory('test', 'first line', 'overwrite');
      await agent.updateMemory('test', 'second line', 'append');
      
      const content = fs.readFileSync(path.join(testMemoryDir, 'test.md'), 'utf8');
      expect(content).toContain('first line');
      expect(content).toContain('second line');
    });
  });

  describe('inferDecision', () => {
    it('should parse JSON decision from Efficient AI response', async () => {
      agent.chat = jest.fn().mockResolvedValue({
        content: '{"action":"reflect","priority":"low","reasoning":"test"}',
        provider: 'engine',
        model: 'local-engine',
        latency_ms: 5,
        cost: 0,
        savings: 0,
        cache_hit: false,
        intent: 'structured_generation',
        complexity: 'simple',
      });

      const decision = await agent.inferDecision('system prompt', { decision_waterfall: { content: '' } });

      expect(decision.action).toBe('reflect');
      expect(decision.priority).toBe('low');
      expect(decision._routing.provider).toBe('engine');
    });

    it('should default to scan_gigs when JSON parse fails', async () => {
      agent.chat = jest.fn().mockResolvedValue({
        content: 'not valid json',
        provider: 'engine',
        model: 'local-engine',
        latency_ms: 5,
        cost: 0,
        savings: 0,
        cache_hit: false,
        intent: 'unknown',
        complexity: 'simple',
      });

      const decision = await agent.inferDecision('system prompt', { decision_waterfall: { content: '' } });

      expect(decision.action).toBe('scan_gigs');
      expect(decision.priority).toBe('high');
    });
  });

  describe('generateStateYAML', () => {
    it('should generate valid YAML with decision and routing metadata', () => {
      const decision = {
        action: 'test',
        priority: 'high',
        reasoning: 'testing',
        _routing: { provider: 'engine', model: 'local-engine', cost: 0.001, savings: 0.01, cache_hit: true },
      };
      const yaml = agent.generateStateYAML(decision);

      expect(yaml).toContain('phase: active');
      expect(yaml).toContain('last_action: test');
      expect(yaml).toContain('last_provider: engine');
      expect(yaml).toContain('cache_hit: true');
    });
  });
});
