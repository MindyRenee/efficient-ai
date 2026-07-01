# x402 Monetization Guide

Efficient AI can monetize API calls using the x402 payment protocol, enabling per-request micropayments in USDC.

## Overview

x402 is an AI-native payment protocol that revives the HTTP 402 "Payment Required" status code for real-time micropayments. Clients pay per-request using cryptocurrency (USDC on Base or Solana), and your server validates payments before processing.

## Pricing Model

Efficient AI uses dynamic pricing based on which backend handles the request:

| Tier | Backend | Price per Request | Description |
|------|---------|-------------------|-------------|
| **engine** | Embedded deterministic engine | $0.0001 | 88% of queries - basically free |
| **ollama** | Local model inference | $0.001 | Cheaper than any cloud API |
| **cloud** | Cloud fallback (GPT-4o, etc.) | $0.01 | Pass-through + small markup |

**Example**: A customer making 1,000 requests would pay:
- 880 engine requests @ $0.0001 = $0.088
- 100 Ollama requests @ $0.001 = $0.10
- 20 cloud requests @ $0.01 = $0.20
- **Total: $0.388** (vs ~$50 on OpenAI directly)

## Quick Start

### 1. Get a Wallet Address

Create an EVM wallet address to receive USDC payments:
- Base mainnet (default): Use any EVM wallet (MetaMask, Coinbase Wallet, etc.)
- Solana: Use a Solana wallet address

### 2. Set Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your wallet address
EFFICIENT_WALLET=0xYourWalletAddressHere
```

### 3. Start the Server

#### Local Development
```bash
# Install with proxy dependencies
pip install -e ".[proxy]"

# Start the server (free mode without wallet)
efficient serve --port 8000

# Start with x402 payments enabled
EFFICIENT_WALLET=0xYourWalletAddress efficient serve --port 8000
```

#### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up -d

# Or build and run manually
docker build -t efficient-ai .
docker run -p 8000:8000 -e EFFICIENT_WALLET=0xYourWalletAddress efficient-ai
```

### 4. Test the Endpoint

```bash
# Test request (free mode - no payment required)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "What is 2 + 2?"}]}'

# With wallet set, this returns 402 with payment requirements
# Response includes PAYMENT-REQUIRED header with payment manifest
```

## Payment Flow

### Without Payment (Free Mode)
```
Client → POST /v1/chat/completions
Server → 200 OK + response (no payment required)
```

### With Payment (Production)
```
Client → POST /v1/chat/completions
Server → 402 Payment Required + PAYMENT-REQUIRED header
Client → Signs payment using x402 SDK
Client → POST /v1/chat/completions + PAYMENT-SIGNATURE header
Server → Verifies payment via facilitator
Server → 200 OK + response
```

## Client Integration

Clients using the x402 Python SDK:

```python
from x402 import x402Client
from x402.mechanisms.evm.exact import ExactEvmScheme
import httpx

# Setup x402 client
client = x402Client()
client.register("eip155:8453", ExactEvmScheme(signer=your_signer))

# Make request - x402 automatically handles 402 → pay → retry
response = httpx.post(
    "http://your-server.com/v1/chat/completions",
    json={
        "model": "auto",
        "messages": [{"role": "user", "content": "Hello!"}],
    }
)
print(response.json())
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EFFICIENT_WALLET` | (empty) | EVM wallet address to receive payments |
| `EFFICIENT_NETWORK` | `eip155:8453` | CAIP-2 network identifier (Base mainnet) |
| `EFFICIENT_FACILITATOR_URL` | `https://x402.org/facilitator` | x402 facilitator for payment verification |

### CLI Options

```bash
efficient serve --help

# Options:
#   --host TEXT       Host to bind (default: 0.0.0.0)
#   --port INTEGER   Port to bind (default: 8000)
#   --wallet TEXT     EVM wallet address for receiving x402 payments
#   --network TEXT    CAIP-2 network (default: Base mainnet)
```

## Custom Pricing

To customize pricing, edit `efficient/proxy.py`:

```python
PRICING = {
    "engine": 0.0001,   # Adjust engine pricing
    "ollama": 0.001,    # Adjust Ollama pricing
    "cloud": 0.01,      # Adjust cloud pricing
}
```

## Payment Verification

In production, the server verifies payments via the x402 facilitator API. The verification flow:

1. Client sends payment in `PAYMENT-SIGNATURE` header
2. Server decodes the payment payload
3. Server calls facilitator `/verify` endpoint
4. Facilitator validates the on-chain transaction
5. Server processes request only if verification succeeds

For development/testing without a wallet, the server runs in "free mode" and skips payment verification.

## Deployment

### Production Checklist

- [ ] Set `EFFICIENT_WALLET` to your production wallet address
- [ ] Test payment flow with x402 SDK
- [ ] Configure reverse proxy (nginx/Caddy) for SSL
- [ ] Set up monitoring for payment failures
- [ ] Configure rate limiting to prevent abuse
- [ ] Set up logging for payment tracking

### Example Nginx Config

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Monitoring

The server includes response headers for monitoring:

- `X-Tier`: Which backend handled the request (engine/ollama/cloud)
- `X-Price`: Price charged for this request
- `X-Model`: Model used
- `X-Latency-ms`: Request latency in milliseconds

Use these to track:
- Revenue by tier
- Backend utilization
- Performance metrics

## Security Considerations

1. **Wallet Security**: Never commit your wallet address to public repos if it holds significant funds
2. **Payment Verification**: Always use the facilitator in production - never skip verification
3. **Rate Limiting**: Implement rate limiting to prevent payment abuse
4. **SSL/TLS**: Always use HTTPS in production to protect payment signatures

## Troubleshooting

### Server returns 402 but I have a wallet set
- Check that `EFFICIENT_WALLET` is set correctly
- Verify the wallet address format (0x...)
- Check server logs for errors

### Payment verification fails
- Verify facilitator URL is accessible
- Check that the payment was actually sent on-chain
- Ensure the network matches (Base vs Solana)

### Free mode not working
- Server runs in free mode when `EFFICIENT_WALLET` is empty
- Check environment variable is not set
- Restart server after changing environment variables

## Resources

- [x402 Official Documentation](https://www.x402.org)
- [x402 Python SDK](https://github.com/x402-foundation/python-sdk)
- [Base Network](https://base.org)
- [USDC on Base](https://bridge.base.org/usdc)

## License

MIT License - See LICENSE file for details.
