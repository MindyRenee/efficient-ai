const rateLimit = require('express-rate-limit');
const logger = require('../config/logger');

const createRateLimiter = (windowMs, max, message) => {
  return rateLimit({
    windowMs,
    max,
    message: { error: message },
    handler: (req, res) => {
      logger.warn('Rate limit exceeded', { 
        ip: req.ip, 
        path: req.path 
      });
      res.status(429).json({ error: message });
    },
    standardHeaders: true,
    legacyHeaders: false
  });
};

const apiLimiter = createRateLimiter(
  15 * 60 * 1000, // 15 minutes
  100, // 100 requests per window
  'Too many requests from this IP, please try again later'
);

const authLimiter = createRateLimiter(
  15 * 60 * 1000, // 15 minutes
  5, // 5 requests per window
  'Too many authentication attempts, please try again later'
);

const strictLimiter = createRateLimiter(
  60 * 1000, // 1 minute
  10, // 10 requests per window
  'Too many requests, please slow down'
);

module.exports = { apiLimiter, authLimiter, strictLimiter };
