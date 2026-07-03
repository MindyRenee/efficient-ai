const logger = require('../config/logger');
const config = require('../config/config');

class X402Middleware {
  constructor() {
    this.pricing = {
      'decision_waterfall': 0.01,  // $0.01 in USDC
      'guardrails': 0.02,
      'strategy_weights': 0.01,
      'content_strategy': 0.02,
      'freelance_strategy': 0.02,
      'karma_strategy': 0.01,
      'alpha_strategies': 0.02,  // Premium proprietary content
      'experiment_framework': 0.01,
      'default': config.get('x402.pricing')
    };
    
    this.acceptedNetworks = ['base', 'solana'];
    this.walletAddress = config.get('x402.wallet_address') || null;
    this.network = config.get('x402.network');
    this.enabled = config.get('x402.enabled');
  }

  generateX402Response(price, resource) {
    if (!this.walletAddress) {
      logger.error('Wallet address not configured for x402 payments');
      throw new Error('Wallet address not configured. Please set X402_WALLET_ADDRESS in environment variables.');
    }
    
    return {
      '@context': 'https://x402.org/contexts/v1',
      type: 'PaymentRequired',
      price: {
        amount: price,
        currency: 'USDC',
        networks: this.acceptedNetworks
      },
      payment: {
        address: this.walletAddress,
        timeout: 300000, // 5 minutes
        scheme: 'x402'
      },
      resource: resource,
      timestamp: new Date().toISOString()
    };
  }

  checkPaymentRequest(req, res, next) {
    // Note: Express lowercases all header names automatically
    // So 'X-Payment', 'x-payment', 'X-PAYMENT' all become 'x-payment'
    const paymentHeader = req.headers['x-payment'];
    
    if (!paymentHeader) {
      const resource = req.path;
      const price = this.getPriceForResource(resource);
      
      logger.info('Payment required', { resource, price });
      
      return res.status(402).json(this.generateX402Response(price, resource));
    }
    
    try {
      const payment = JSON.parse(paymentHeader);
      
      if (!this.validatePayment(payment)) {
        logger.warn('Invalid payment', { payment });
        return res.status(402).json(this.generateX402Response(this.getPriceForResource(req.path), req.path));
      }
      
      logger.info('Payment validated', { amount: payment.amount, resource: req.path });
      req.payment = payment;
      next();
    } catch (error) {
      // JSON parsing error - return 400 Bad Request instead of 402 Payment Required
      // This is more appropriate for malformed payment data
      logger.error('Payment validation error - malformed JSON', { error: error.message });
      return res.status(400).json({ 
        error: 'Invalid payment format',
        message: 'Payment header must be valid JSON'
      });
    }
  }

  getPriceForResource(resource) {
    // Extract filename from path (e.g., /api/brain/decision_waterfall -> decision_waterfall)
    const filename = resource.split('/').pop();
    
    // Exact matching to avoid false positives
    if (filename === 'decision_waterfall') return this.pricing['decision_waterfall'];
    if (filename === 'guardrails') return this.pricing['guardrails'];
    if (filename === 'strategy_weights') return this.pricing['strategy_weights'];
    if (filename === 'content_strategy') return this.pricing['content_strategy'];
    if (filename === 'freelance_strategy') return this.pricing['freelance_strategy'];
    if (filename === 'karma_strategy') return this.pricing['karma_strategy'];
    if (filename === 'alpha_strategies') return this.pricing['alpha_strategies'];
    if (filename === 'experiment_framework') return this.pricing['experiment_framework'];
    
    return this.pricing['default'];
  }

  validatePayment(payment) {
    if (!payment.amount || !payment.currency || !payment.transactionHash) {
      return false;
    }
    
    if (payment.currency !== 'USDC') {
      return false;
    }
    
    if (!this.acceptedNetworks.includes(payment.network)) {
      return false;
    }
    
    // SECURITY WARNING: In production, verify transaction on blockchain
    // This is a placeholder that accepts any valid-looking payment
    // TODO: Implement actual blockchain transaction verification using:
    // - ethers.js for Base (Ethereum L2)
    // - @solana/web3.js for Solana
    // - Verify transactionHash exists on-chain
    // - Verify amount matches payment
    // - Verify recipient is walletAddress
    // - Verify transaction is not already spent
    
    if (config.get('env') === 'production') {
      logger.error('Payment verification not implemented in production', { payment });
      return false;
    }
    
    return true;
  }

  setWalletAddress(address) {
    this.walletAddress = address;
    logger.info('Wallet address set', { address });
  }

  setPricing(pricing) {
    this.pricing = { ...this.pricing, ...pricing };
    logger.info('Pricing updated', { pricing: this.pricing });
  }
}

// Export class instead of singleton to allow multiple instances
// This prevents state mutation issues in testing and concurrent scenarios
module.exports = X402Middleware;
