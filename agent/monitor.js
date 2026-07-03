const MarkdownAgent = require('./src/agent/MarkdownAgent');
const MonitorServer = require('./src/monitor/MonitorServer');
const logger = require('./src/config/logger');

const agent = new MarkdownAgent();
const monitor = new MonitorServer(agent);

monitor.start();
agent.start();

logger.info('Monitor server is running. Press Ctrl+C to stop.');

process.on('SIGINT', () => {
  logger.info('Received SIGINT, shutting down gracefully');
  agent.stop();
  monitor.stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  logger.info('Received SIGTERM, shutting down gracefully');
  agent.stop();
  monitor.stop();
  process.exit(0);
});
