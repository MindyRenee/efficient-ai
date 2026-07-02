# Security Best Practices

Comprehensive security guidelines for deploying Efficient AI in production environments.

## Table of Contents

- [Security Overview](#security-overview)
- [Threat Model](#threat-model)
- [Authentication & Authorization](#authentication--authorization)
- [Data Protection](#data-protection)
- [Network Security](#network-security)
- [Application Security](#application-security)
- [Infrastructure Security](#infrastructure-security)
- [Payment Security](#payment-security)
- [Compliance](#compliance)
- [Incident Response](#incident-response)

## Security Overview

Efficient AI implements defense-in-depth security across multiple layers:

1. **Application Layer**: Input validation, output sanitization, rate limiting
2. **Transport Layer**: TLS 1.3, mTLS for service-to-service communication
3. **Infrastructure Layer**: Network segmentation, firewall rules, IAM policies
4. **Payment Layer**: x402 protocol with cryptographic verification
5. **Data Layer**: Encryption at rest, secure key management

## Threat Model

### Identified Threats

|Threat|Likelihood|Impact|Mitigation|
|--------|-----------|--------|------------|
|DDoS attacks|High|Medium|Rate limiting, CDN, auto-scaling|
|API key leakage|Medium|High|Secrets management, rotation|
|Payment fraud|Medium|High|x402 verification, facilitator|
|Data exfiltration|Low|High|Encryption, access controls|
|Supply chain attacks|Low|High|Dependency scanning, SBOM|
|Insider threats|Low|High|Audit logging, least privilege|

### Attack Surface

```text
┌─────────────────────────────────────────────────────────┐
│                   External Attack Surface                │
├─────────────────────────────────────────────────────────┤
│  • Public API endpoint (port 443)                        │
│  • x402 payment verification (facilitator API)           │
│  • Cloud API keys (if configured)                         │
│  • Ollama backend (if exposed)                           │
└─────────────────────────────────────────────────────────┘
```

## Authentication & Authorization

### API Key Authentication

**Implementation**:

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != os.getenv("API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )
    return api_key_header

@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: str = Security(get_api_key)
):
    # Process request
    pass
```

**Best Practices**:

- Use cryptographically secure random keys (32+ bytes)
- Rotate keys every 90 days
- Implement key expiration
- Use different keys for different environments
- Log all authentication attempts

### JWT Authentication

**For enterprise clients**:

```python
import jwt
from datetime import datetime, timedelta

def create_jwt_token(user_id: str, secret: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_jwt_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### Role-Based Access Control (RBAC)

```python
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    READ_ONLY = "read_only"

class User:
    def __init__(self, user_id: str, role: Role):
        self.user_id = user_id
        self.role = role

def check_permission(user: User, required_role: Role) -> bool:
    role_hierarchy = {
        Role.READ_ONLY: 1,
        Role.USER: 2,
        Role.ADMIN: 3,
    }
    return role_hierarchy[user.role] >= role_hierarchy[required_role]
```

## Data Protection

### Encryption at Rest

**Database encryption**:

```sql
-- PostgreSQL TDE (Transparent Data Encryption)
-- Enable in postgresql.conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

**File system encryption**:

```bash
# LUKS encryption for data volumes
cryptsetup -y -v luksFormat /dev/sdb1
cryptsetup luksOpen /dev/sdb1 encrypted_data
mkfs.ext4 /dev/mapper/encrypted_data
mount /dev/mapper/encrypted_data /data
```

**Cache encryption** (Redis):

```bash
# Enable Redis encryption with TLS
redis-server --tls-port 6379 --port 0 \
  --tls-cert-file /path/to/redis.crt \
  --tls-key-file /path/to/redis.key \
  --tls-ca-cert-file /path/to/ca.crt
```

### Encryption in Transit

**TLS 1.3 configuration**:

```nginx
ssl_protocols TLSv1.3 TLSv1.2;
ssl_ciphers 'TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256';
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 10m;
```

**mTLS for service-to-service**:

```python
from fastapi import Request
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)

# Verify client certificates
@app.middleware("http")
async def verify_mtls(request: Request, call_next):
    client_cert = request.scope.get("client_cert")
    if not client_cert:
        raise HTTPException(status_code=403, detail="Client certificate required")
    response = await call_next(request)
    return response
```

### Secrets Management

**HashiCorp Vault integration**:

```python
import hvac

class VaultSecrets:
    def __init__(self, vault_addr: str, token: str):
        self.client = hvac.Client(url=vault_addr, token=token)
    
    def get_secret(self, path: str) -> dict:
        response = self.client.secrets.kv.v2.read_secret_version(path=path)
        return response['data']['data']
    
    def get_api_key(self) -> str:
        return self.get_secret("secret/efficient-ai")["api_key"]
```

**AWS Secrets Manager**:

```python
import boto3

def get_secret(secret_name: str, region_name: str = "us-east-1") -> dict:
    client = boto3.client('secretsmanager', region_name=region_name)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])
```

## Network Security

### Firewall Configuration

**UFW rules**:

```bash
# Default deny
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (restrict to specific IPs)
ufw allow from 203.0.113.0/24 to any port 22 proto tcp

# Allow HTTPS
ufw allow 443/tcp

# Allow internal communication
ufw allow from 10.0.0.0/8 to any port 8000 proto tcp

# Enable
ufw enable
```

**Security groups (AWS)**:

```json
{
  "InboundRules": [
    {
      "IpProtocol": "tcp",
      "FromPort": 443,
      "ToPort": 443,
      "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
    },
    {
      "IpProtocol": "tcp",
      "FromPort": 22,
      "ToPort": 22,
      "IpRanges": [{"CidrIp": "203.0.113.0/24"}]
    }
  ]
}
```

### Network Segmentation

**VPC architecture**:

```text
┌─────────────────────────────────────────────────┐
│                    VPC                          │
│  ┌──────────────┐  ┌──────────────┐            │
│  │ Public Subnet│  │Private Subnet│            │
│  │  (Load Bal)  │  │  (App Servers)│           │
│  └──────────────┘  └──────────────┘            │
│                         │                       │
│                  ┌──────▼──────┐                │
│                  │Private Subnet│                │
│                  │  (Database)  │                │
│                  └──────────────┘                │
└─────────────────────────────────────────────────┘
```

### DDoS Protection

**Cloudflare configuration**:

1. Enable "Under Attack Mode" during attacks
2. Set rate limits: 100 requests/minute per IP
3. Enable bot protection
4. Configure page rules for sensitive endpoints

**Application-level rate limiting**:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/v1/chat/completions")
@limiter.limit("10/minute")
async def chat_completions(request: Request):
    # Process request
    pass
```

## Application Security

### Input Validation

**Pydantic models**:

```python
from pydantic import BaseModel, validator, Field
from typing import List, Optional

class ChatMessage(BaseModel):
    role: str = Field(..., regex="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=10000)
    
    @validator('content')
    def sanitize_content(cls, v):
        # Remove potentially dangerous content
        import re
        v = re.sub(r'<script[^>]*>.*?</script>', '', v, flags=re.IGNORECASE)
        return v

class ChatCompletionRequest(BaseModel):
    model: str = Field(default="auto", max_length=100)
    messages: List[ChatMessage] = Field(..., min_items=1, max_items=50)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32768)
```

### Output Sanitization

**XSS prevention**:

```python
import html

def sanitize_output(text: str) -> str:
    return html.escape(text)

# In response
response.content = sanitize_output(generated_content)
```

### SQL Injection Prevention

**Use parameterized queries**:

```python
# BAD (vulnerable)
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# GOOD (safe)
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### Dependency Security

**Automated scanning**:

```bash
# Use pip-audit
pip install pip-audit
pip-audit

# Use safety
pip install safety
safety check

# Use Snyk
pip install snyk
snyk test
```

**Software Bill of Materials (SBOM)**:

```bash
# Generate SBOM with CycloneDX
pip install cyclonedx-bom
cyclonedx-py -o sbom.json
```

## Infrastructure Security

### Container Security

**Docker security best practices**:

```dockerfile
# Use minimal base image
FROM python:3.12-slim

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Read-only root filesystem
RUN chmod -R 555 /app

# Drop capabilities
--cap-drop=ALL
--cap-add=NET_BIND_SERVICE
```

**Kubernetes security context**:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault
  capabilities:
    drop:
    - ALL
    add:
    - NET_BIND_SERVICE
```

### Image Scanning

**Trivy scanner**:

```bash
# Scan Docker image
trivy image efficient-ai:latest

# Scan in CI/CD
trivy image --exit-code 1 --severity HIGH,CRITICAL efficient-ai:latest
```

### IAM Policies

**Least privilege principle**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:efficient-ai/*"
    }
  ]
}
```

## Payment Security

### x402 Payment Verification

**Payment flow security**:

1. **Client signs payment** using private key
2. **Server verifies signature** using facilitator
3. **Facilitator validates** on-chain transaction
4. **Server only processes** after successful verification

**Implementation**:

```python
async def _verify_payment(payment_header: str, requirements: dict) -> bool:
    if not wallet:
        return True  # Free mode
    
    try:
        payload = _decode_payment_payload(payment_header)
        
        # Verify payment via facilitator
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{facilitator_url}/verify",
                json={
                    "paymentPayload": payload,
                    "paymentRequirements": requirements,
                },
                timeout=10.0,
            )
            
            if resp.status_code != 200:
                logger.warning("Payment verification failed", status=resp.status_code)
                return False
            
            # Additional validation
            result = resp.json()
            if not result.get("verified", False):
                logger.warning("Payment not verified on-chain")
                return False
            
            # Check amount matches
            paid_amount = result.get("amount", 0)
            required_amount = int(requirements["price"]["amount"])
            if paid_amount < required_amount:
                logger.warning("Insufficient payment", paid=paid_amount, required=required_amount)
                return False
            
            return True
            
    except Exception as e:
        logger.error("Payment verification error", error=str(e))
        return False
```

### Wallet Security

**Best practices**:

1. **Hardware wallets** for production (Ledger, Trezor)
2. **Multi-sig wallets** for high-value operations
3. **Separate wallets** for development and production
4. **Regular balance monitoring**
5. **Transaction signing** in secure environment

**Multi-sig example**:

```python
# 2-of-3 multi-sig wallet
from web3 import Web3

w3 = Web3()
wallet_address = "0x..."  # Multi-sig contract address

# Requires 2 of 3 signatures to spend
signatures_required = 2
```

## Compliance

### SOC 2 Type II Controls

**Access Control**:

- Unique user accounts for all personnel
- MFA required for privileged access
- Access reviews quarterly
- Automated provisioning/deprovisioning

**Change Management**:

- All changes via pull requests
- Code review required
- Approval process for production changes
- Rollback procedures documented

**Incident Response**:

- 24/7 monitoring
- Incident response team on-call
- Defined escalation procedures
- Post-incident reviews

### GDPR Compliance

**Data minimization**:

- Only collect necessary data
- Automatic data retention policies
- Right to deletion implementation

**Data portability**:

- Export user data on request
- Standard formats (JSON, CSV)
- Timely response (30 days)

**Consent management**:

- Explicit consent for data processing
- Easy withdrawal of consent
- Clear privacy policy

### PCI DSS (if applicable)

**Payment card data**:

- Never store full card numbers
- Use tokenization
- PCI-compliant payment processor
- Regular vulnerability scanning

## Incident Response

### Incident Classification

|Severity|Response Time|Example|
|----------|---------------|---------|
|P0 - Critical|15 minutes|System down, data breach|
|P1 - High|1 hour|Payment failures, security vulnerability|
|P2 - Medium|4 hours|Performance degradation, minor bugs|
|P3 - Low|24 hours|Documentation issues, feature requests|

### Incident Response Plan

1. **Detection**:
   - Automated alerts trigger
   - On-call engineer notified

2. **Containment**:
   - Isolate affected systems
   - Block malicious traffic
   - Disable vulnerable features

3. **Eradication**:
   - Identify root cause
   - Apply patches
   - Remove malicious code

4. **Recovery**:
   - Restore from backups
   - Verify system integrity
   - Resume normal operations

5. **Post-Incident**:
   - Document incident
   - Conduct post-mortem
   - Implement improvements

### Security Incident Reporting

**Report template**:

```markdown
# Security Incident Report

## Summary
[Brief description]

## Timeline
- [ ] Detection time
- [ ] Containment time
- [ ] Eradication time
- [ ] Recovery time

## Impact
- Data affected: [list]
- Users affected: [number]
- Revenue impact: [amount]

## Root Cause
[Analysis]

## Remediation
[Actions taken]

## Prevention
[Future measures]
```

## Security Audits

### Regular Audits

**Monthly**:

- Dependency vulnerability scan
- Access review
- Log analysis

**Quarterly**:

- Penetration testing
- Code security review
- Configuration audit

**Annually**:

- Third-party security assessment
- Compliance audit (SOC 2, PCI DSS)
- Disaster recovery test

### Penetration Testing

**Scope**:

- Public API endpoints
- Authentication mechanisms
- Payment verification
- Infrastructure

**Tools**:

- OWASP ZAP
- Burp Suite
- Metasploit
- Nmap

## Security Checklist

### Pre-Deployment

- [ ] All secrets in secrets manager
- [ ] TLS 1.3 enabled
- [ ] Rate limiting configured
- [ ] Input validation implemented
- [ ] Output sanitization implemented
- [ ] Dependencies scanned
- [ ] Security headers configured
- [ ] Firewall rules applied
- [ ] Monitoring configured
- [ ] Incident response plan ready

### Post-Deployment

- [ ] Security monitoring active
- [ ] Alerts configured
- [ ] Log aggregation working
- [ ] Backup verification complete
- [ ] Team trained on procedures

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [x402 Security Documentation](https://www.x402.org/security)
