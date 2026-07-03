const convict = require('convict');
const path = require('path');

const config = convict({
  env: {
    doc: 'The application environment.',
    format: ['production', 'development', 'test'],
    default: 'development',
    env: 'NODE_ENV'
  },
  agent: {
    cycle_interval_minutes: {
      doc: 'Agent cycle interval in minutes',
      format: 'int',
      default: 30,
      env: 'AGENT_CYCLE_INTERVAL'
    },
    max_concurrent_cycles: {
      doc: 'Maximum concurrent agent cycles',
      format: 'int',
      default: 1,
      env: 'AGENT_MAX_CONCURRENT_CYCLES'
    }
  },
  monitor: {
    port: {
      doc: 'Monitor server port',
      format: 'port',
      default: 3001,
      env: 'MONITOR_PORT'
    }
  },
  logging: {
    level: {
      doc: 'Log level',
      format: ['error', 'warn', 'info', 'debug'],
      default: 'info',
      env: 'LOG_LEVEL'
    },
    dir: {
      doc: 'Log directory',
      format: String,
      default: path.join(__dirname, '../../logs')
    }
  },
  security: {
    jwt_secret: {
      doc: 'JWT secret for authentication',
      format: String,
      default: 'change-this-in-production',
      env: 'JWT_SECRET'
    },
    bcrypt_rounds: {
      doc: 'Bcrypt rounds for password hashing',
      format: 'int',
      default: 10,
      env: 'BCRYPT_ROUNDS'
    },
    rate_limit_window_ms: {
      doc: 'Rate limit window in milliseconds',
      format: 'int',
      default: 900000,
      env: 'RATE_LIMIT_WINDOW_MS'
    },
    rate_limit_max_requests: {
      doc: 'Maximum requests per window',
      format: 'int',
      default: 100,
      env: 'RATE_LIMIT_MAX_REQUESTS'
    }
  },
  efficient: {
    host: {
      doc: 'Efficient AI local server URL',
      format: String,
      default: 'http://localhost:8000',
      env: 'EFFICIENT_HOST'
    }
  },
  storage: {
    brain_dir: {
      doc: 'Brain files directory',
      format: String,
      default: path.join(__dirname, '../../brain')
    },
    memory_dir: {
      doc: 'Memory files directory',
      format: String,
      default: path.join(__dirname, '../../memory')
    },
    max_log_size_mb: {
      doc: 'Maximum daily log size in MB',
      format: 'int',
      default: 10,
      env: 'MAX_LOG_SIZE_MB'
    }
  },
  api: {
    reddit: {
      client_id: {
        doc: 'Reddit API client ID',
        format: String,
        default: '',
        env: 'REDDIT_CLIENT_ID'
      },
      client_secret: {
        doc: 'Reddit API client secret',
        format: String,
        default: '',
        env: 'REDDIT_CLIENT_SECRET'
      },
      user_agent: {
        doc: 'Reddit API user agent',
        format: String,
        default: 'MarkdownAgent/2.0',
        env: 'REDDIT_USER_AGENT'
      }
    },
    medium: {
      api_key: {
        doc: 'Medium API key',
        format: String,
        default: '',
        env: 'MEDIUM_API_KEY'
      }
    },
    openai: {
      api_key: {
        doc: 'OpenAI API key',
        format: String,
        default: '',
        env: 'OPENAI_API_KEY'
      }
    }
  },
  x402: {
    enabled: {
      doc: 'Enable x402 payment protocol',
      format: Boolean,
      default: true,
      env: 'X402_ENABLED'
    },
    wallet_address: {
      doc: 'USDC wallet address for payments',
      format: String,
      default: '',
      env: 'X402_WALLET_ADDRESS'
    },
    network: {
      doc: 'Blockchain network (base or solana)',
      format: ['base', 'solana'],
      default: 'base',
      env: 'X402_NETWORK'
    },
    pricing: {
      doc: 'Default price in USDC',
      format: Number,
      default: 0.005,
      env: 'X402_DEFAULT_PRICE'
    }
  }
});

config.validate({ allowed: 'strict' });

module.exports = config;
