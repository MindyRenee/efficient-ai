# API Reference

Complete API documentation for Efficient AI's OpenAI-compatible endpoints with x402 monetization.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Base URL](#base-url)
- [Endpoints](#endpoints)
- [Response Format](#response-format)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [x402 Payment Protocol](#x402-payment-protocol)
- [SDK Examples](#sdk-examples)

## Overview

Efficient AI provides an OpenAI-compatible API that automatically routes requests to the most cost-effective backend:

- **Embedded engine** (88% of queries): $0.0001, <1ms latency
- **Ollama local** (10% of queries): $0.001, local inference
- **Cloud fallback** (2% of queries): $0.01, GPT-4o/Claude/etc.

The API is fully compatible with OpenAI's Python SDK - just change the base URL.

## Authentication

### API Key Authentication

```bash
curl -X POST https://api.yourdomain.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Hello"}]}'
```

### x402 Payment Authentication

```bash
# First request returns 402 with payment requirements
curl -X POST https://api.yourdomain.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Hello"}]}'

# Response includes PAYMENT-REQUIRED header
# Client signs payment and retries with PAYMENT-SIGNATURE header
```

## Base URL

|Environment|Base URL|
|-------------|----------|
|Production|`https://api.yourdomain.com`|
|Staging|`https://staging-api.yourdomain.com`|
|Development|`http://localhost:8000`|

## Endpoints

### Chat Completions

Create a chat completion.

**Endpoint**: `POST /v1/chat/completions`

**Request Body**:

```json
{
  "model": "auto",
  "messages": [
    {
      "role": "user",
      "content": "What is the capital of France?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false,
  "response_format": null
}
```

**Parameters**:

|Parameter|Type|Required|Default|Description|
|-----------|------|----------|---------|-------------|
|`model`|string|No|`auto`|Model to use. `auto` for automatic routing, or specific model name|
|`messages`|array|Yes|-|Array of message objects|
|`temperature`|number|No|`0.7`|Sampling temperature (0.0 to 2.0)|
|`max_tokens`|integer|No|`null`|Maximum tokens to generate|
|`stream`|boolean|No|`false`|Enable streaming response|
|`response_format`|object|No|`null`|Format for structured output (e.g., `{"type": "json_object"}`)|

**Message Object**:

|Parameter|Type|Required|Description|
|-----------|------|----------|-------------|
|`role`|string|Yes|`system`, `user`, or `assistant`|
|`content`|string|Yes|Message content|

**Response** (non-streaming):

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1699012345,
  "model": "local-engine",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "The capital of France is Paris."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

**Response Headers**:

| Header | Description |
|--------|-------------|
| `X-Tier` | Backend used (`engine`, `ollama`, `cloud`) |
| `X-Price` | Price charged for this request |
| `X-Model` | Model used |
| `X-Latency-ms` | Request latency in milliseconds |

**Example**:

```bash
curl -X POST https://api.yourdomain.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'
```

### List Models

List available models.

**Endpoint**: `GET /v1/models`

**Response**:

```json
{
  "object": "list",
  "data": [
    {
      "id": "auto",
      "object": "model",
      "owned_by": "efficient"
    },
    {
      "id": "local-engine",
      "object": "model",
      "owned_by": "efficient"
    }
  ]
}
```

### Health Check

Check service health.

**Endpoint**: `GET /health`

**Response**:

```json
{
  "status": "ok",
  "engine": "available"
}
```

### Root Endpoint

Get service information.

**Endpoint**: `GET /`

**Response**:

```json
{
  "service": "Efficient AI Proxy",
  "version": "0.1.0",
  "pricing": {
    "engine": 0.0001,
    "ollama": 0.001,
    "cloud": 0.01
  },
  "wallet": "0x123...abc",
  "network": "eip155:8453",
  "endpoints": {
    "chat": "/v1/chat/completions",
    "models": "/v1/models",
    "health": "/health"
  }
}
```

## Response Format

### ChatCompletion Object

```typescript
interface ChatCompletion {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: Choice[];
  usage: Usage;
}

interface Choice {
  index: number;
  message: Message;
  finish_reason: "stop" | "length" | "content_filter";
}

interface Message {
  role: "assistant";
  content: string;
}

interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}
```

### Streaming Response

When `stream: true`, responses are sent as Server-Sent Events (SSE):

```text
data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"role":"assistant","content":"The"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"content":" capital"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"content":" of"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"content":" France"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"content":" is"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{"content":" Paris"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","created":1699012345,"model":"local-engine","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Error Handling

### Error Response Format

```json
{
  "error": {
    "message": "Error description",
    "type": "error_type",
    "param": null,
    "code": null
  }
}
```

### HTTP Status Codes

|Code|Description|
|------|-------------|
|200|Success|
|400|Bad Request|
|401|Unauthorized|
|402|Payment Required (x402)|
|429|Rate Limit Exceeded|
|500|Internal Server Error|
|503|Service Unavailable|

### Error Types

|Type|Description|
|------|-------------|
|`invalid_request_error`|Invalid request parameters|
|`authentication_error`|Authentication failed|
|`payment_required`|Payment required (x402)|
|`rate_limit_error`|Rate limit exceeded|
|`internal_error`|Internal server error|

### Example Error Response

```json
{
  "error": {
    "message": "Invalid API key",
    "type": "authentication_error",
    "param": null,
    "code": null
  }
}
```

## Rate Limiting

### Default Limits

| Plan | Requests/Minute | Requests/Day |
|------|-----------------|--------------|
| Free | 10 | 1,000 |
| Basic | 100 | 10,000 |
| Pro | 1,000 | 100,000 |
| Enterprise | Custom | Custom |

### Rate Limit Headers

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Request limit |
| `X-RateLimit-Remaining` | Remaining requests |
| `X-RateLimit-Reset` | Unix timestamp when limit resets |

### Rate Limit Exceeded Response

```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error",
    "param": null,
    "code": null
  }
}
```

## x402 Payment Protocol

### Payment Flow

1. **Initial Request**: Client sends request without payment
2. **402 Response**: Server returns payment requirements
3. **Payment**: Client signs payment using x402 SDK
4. **Retry**: Client resends request with `PAYMENT-SIGNATURE` header
5. **Verification**: Server verifies payment via facilitator
6. **Success**: Server processes request and returns response

### Payment Requirements Response

**Status Code**: 402

**Headers**:
- `PAYMENT-REQUIRED`: Base64-encoded payment requirements
- `X-Price`: Price in USD
- `X-Tier`: Backend tier

**Body**:

```json
{
  "scheme": "exact",
  "network": "eip155:8453",
  "pay_to": "0x123...abc",
  "price": {
    "amount": "100",
    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "extra": {
      "name": "USDC",
      "version": "2"
    }
  },
  "description": "Efficient AI — chat completion",
  "mimeType": "application/json"
}
```

### Payment Request

**Headers**:
- `PAYMENT-SIGNATURE`: Base64-encoded signed payment payload

**Example**:

```bash
curl -X POST https://api.yourdomain.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "PAYMENT-SIGNATURE: eyJwYXltZW50UGF5bG9hZCI6..." \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

## SDK Examples

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.yourdomain.com/v1",
    api_key="your-api-key"
)

response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "What is 2 + 2?"}
    ]
)

print(response.choices[0].message.content)
```

### Python (x402 SDK)

```python
from x402 import x402Client
from x402.mechanisms.evm.exact import ExactEvmScheme
import httpx

# Setup x402 client
x402_client = x402Client()
x402_client.register("eip155:8453", ExactEvmScheme(signer=your_signer))

# Make request - x402 automatically handles 402 → pay → retry
response = httpx.post(
    "https://api.yourdomain.com/v1/chat/completions",
    json={
        "model": "auto",
        "messages": [{"role": "user", "content": "Hello!"}],
    }
)
print(response.json())
```

### JavaScript

```javascript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.yourdomain.com/v1',
  apiKey: 'your-api-key'
});

const response = await client.chat.completions.create({
  model: 'auto',
  messages: [
    { role: 'user', content: 'What is 2 + 2?' }
  ]
});

console.log(response.choices[0].message.content);
```

### cURL

```bash
curl -X POST https://api.yourdomain.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'
```

### Streaming Example (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.yourdomain.com/v1",
    api_key="your-api-key"
)

stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Structured Output Example

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.yourdomain.com/v1",
    api_key="your-api-key"
)

response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "user", "content": "Extract the email from: Contact john@test.com"}
    ],
    response_format={"type": "json_object"}
)

print(response.choices[0].message.content)
```

## Model Reference

### Auto Routing

When `model="auto"`, Efficient AI automatically routes to the optimal backend:

| Query Type | Backend | Price | Latency |
|-------------|---------|-------|---------|
| Simple Q&A | Engine | $0.0001 | <1ms |
| Summarization | Engine | $0.0001 | <1ms |
| Classification | Engine | $0.0001 | <1ms |
| Entity extraction | Engine | $0.0001 | <1ms |
| Code generation | Engine | $0.0001 | <1ms |
| Complex reasoning | Ollama | $0.001 | 50-200ms |
| Creative writing | Ollama | $0.001 | 100-300ms |
| Agentic workflows | Cloud | $0.01 | 500-2000ms |

### Specific Models

**Local Models (Ollama)**:
- `phi3:mini` - 3.8B params, 2.3GB VRAM
- `qwen2.5:7b` - 7B params, 4.5GB VRAM
- `llama3.1:8b` - 8B params, 5GB VRAM
- `qwen2.5:14b` - 14B params, 9GB VRAM
- `llama3.3:70b` - 70B params, 40GB VRAM

**Cloud Models**:
- `gpt-4o-mini` - $0.15/M input, $0.60/M output
- `gpt-4o` - $2.50/M input, $10.00/M output
- `claude-3-5-haiku` - $0.80/M input, $4.00/M output
- `claude-sonnet-4` - $3.00/M input, $15.00/M output

## Best Practices

### Optimize for Engine Routing

To maximize engine routing (cheapest, fastest):

- Use clear, direct questions
- Avoid multi-step reasoning in single requests
- Use structured output for data extraction
- Provide context in system messages

### Batch Requests

For multiple independent requests, use parallel requests:

```python
import asyncio
from openai import OpenAI

client = OpenAI(base_url="https://api.yourdomain.com/v1", api_key="key")

async def process_query(query):
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": query}]
    )
    return response.choices[0].message.content

queries = ["What is 2+2?", "Capital of France?", "Summarize this text"]
results = await asyncio.gather(*[process_query(q) for q in queries])
```

### Error Handling

```python
from openai import OpenAI, APIError, RateLimitError

client = OpenAI(base_url="https://api.yourdomain.com/v1", api_key="key")

try:
    response = client.chat.completions.create(
        model="auto",
        messages=[{"role": "user", "content": "Hello"}]
    )
except RateLimitError:
    # Implement exponential backoff
    time.sleep(2)
except APIError as e:
    # Log error and handle appropriately
    print(f"API Error: {e}")
```

## Additional Resources

- [x402 Monetization Guide](./X402_MONETIZATION.md)
- [Deployment Guide](./DEPLOYMENT.md)
- [Security Best Practices](./SECURITY.md)
- [Monitoring Guide](./MONITORING.md)
- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference)
