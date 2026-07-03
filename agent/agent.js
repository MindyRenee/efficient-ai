const MarkdownAgent = require('./src/agent/MarkdownAgent');
const logger = require('./src/config/logger');
const config = require('./src/config/config');

const agent = new MarkdownAgent();

agent.start();

logger.info('Agent is running. Press Ctrl+C to stop.');

process.on('SIGINT', () => {
  logger.info('Received SIGINT, shutting down gracefully');
  agent.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  logger.info('Received SIGTERM, shutting down gracefully');
  agent.stop();
  process.exit(0);
});
