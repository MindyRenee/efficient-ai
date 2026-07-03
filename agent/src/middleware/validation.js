const Joi = require('joi');
const logger = require('../config/logger');

const validateRequest = (schema) => {
  return (req, res, next) => {
    const { error } = schema.validate(req.body);
    
    if (error) {
      logger.warn('Validation failed', { error: error.details });
      return res.status(400).json({ 
        error: 'Validation failed', 
        details: error.details.map(d => d.message) 
      });
    }
    
    next();
  };
};

const validateFileName = (req, res, next) => {
  const fileName = req.params.file;
  
  if (!fileName || !/^[a-zA-Z0-9_-]+$/.test(fileName)) {
    logger.warn('Invalid file name', { fileName });
    return res.status(400).json({ error: 'Invalid file name' });
  }
  
  next();
};

const schemas = {
  login: Joi.object({
    username: Joi.string().alphanum().min(3).max(30).required(),
    password: Joi.string().min(8).required()
  }),
  
  register: Joi.object({
    username: Joi.string().alphanum().min(3).max(30).required(),
    password: Joi.string().min(8).pattern(new RegExp('^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#\$%\^&\*])')).required(),
    email: Joi.string().email().required()
  })
};

module.exports = { validateRequest, validateFileName, schemas };
