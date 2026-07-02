# Enterprise Deployment Guide

Production deployment strategies for Efficient AI with x402 monetization.

## Table of Contents

- [Deployment Architectures](#deployment-architectures)
- [Infrastructure Requirements](#infrastructure-requirements)
- [Security Hardening](#security-hardening)
- [Scaling Strategies](#scaling-strategies)
- [High Availability](#high-availability)
- [Monitoring & Observability](#monitoring--observability)
- [Disaster Recovery](#disaster-recovery)
- [Compliance](#compliance)

## Deployment Architectures

### Single-Region Deployment

**Best for**: Startups, MVPs, low-to-medium traffic

```text
┌─────────────────┐
│   Load Balancer │ (nginx/Caddy/ALB)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│ App 1 │ │ App 2 │ (Efficient AI instances)
└───┬───┘ └───┬────┘
    │         │
    └────┬────┘
         │
┌────────▼─────────┐
│   Shared Cache   │ (Redis/SQLite)
└──────────────────┘
```

**Configuration**:

- 2-3 app instances for redundancy
- Shared cache (Redis) for consistency
- Load balancer with health checks
- Database for telemetry (PostgreSQL)

### Multi-Region Deployment

**Best for**: Enterprise, global customers, high availability

```text
Region US-East                    Region EU-West
┌─────────────────┐              ┌─────────────────┐
│   Load Balancer │              │   Load Balancer │
└────────┬────────┘              └────────┬────────┘
         │                               │
    ┌────┴────┐                      ┌────┴────┐
    │ App Pods │                      │ App Pods │
    └────┬────┘                      └────┬────┘
         │                               │
    ┌────▼────┐                      ┌────▼────┐
    │ Redis   │                      │ Redis   │
    └─────────┘                      └─────────┘
         │                               │
         └──────────────┬────────────────┘
                        │
                 ┌──────▼──────┐
                 │   Global DB  │ (PostgreSQL with read replicas)
                 └─────────────┘
```

**Configuration**:

- GeoDNS routing (Cloudflare, Route53)
- Regional app instances
- Regional Redis clusters
- Global database with read replicas
- Cross-region replication for cache

### Kubernetes Deployment

**Best for**: Cloud-native, auto-scaling, enterprise orchestration

The project includes pre-configured Kubernetes manifests in the `k8s/` directory:

- `k8s/deployment.yaml` - Deployment with 3 replicas, resource limits, and health checks
- `k8s/service.yaml` - LoadBalancer service for external access
- `k8s/secret.yaml` - Kubernetes secret for wallet address
- `k8s/hpa.yaml` - Horizontal Pod Autoscaler for auto-scaling

**Deploy to Kubernetes**:

```bash
# Build and push Docker image
docker build -t efficient-ai:latest .
docker tag efficient-ai:latest your-registry/efficient-ai:latest
docker push your-registry/efficient-ai:latest

# Update secret with your wallet address
kubectl create secret generic efficient-ai-secrets \
  --from-literal=wallet-address=0xYOUR_WALLET_ADDRESS

# Apply manifests
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/hpa.yaml

# Check deployment
kubectl get pods -l app=efficient-ai-proxy
kubectl get svc efficient-ai-proxy
```

## Infrastructure Requirements

### Minimum (Single Instance)

- **CPU**: 2 cores
- **RAM**: 4 GB
- **Storage**: 20 GB SSD
- **Network**: 100 Mbps
- **OS**: Ubuntu 22.04 LTS / Debian 12

### Recommended (Production)

- **CPU**: 4-8 cores per instance
- **RAM**: 8-16 GB per instance
- **Storage**: 50 GB SSD (logs + cache)
- **Network**: 1 Gbps
- **OS**: Ubuntu 22.04 LTS
- **GPU**: Optional (for Ollama backend)

### High-Performance (Enterprise)

- **CPU**: 16+ cores per instance
- **RAM**: 32+ GB per instance
- **Storage**: 200 GB NVMe
- **Network**: 10 Gbps
- **GPU**: NVIDIA A100/H100 (for local LLM)
- **CDN**: Cloudflare / Fastly for static assets

## Security Hardening

### Network Security

```nginx
# nginx configuration example
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL configuration
    ssl_certificate /etc/ssl/certs/yourdomain.crt;
    ssl_certificate_key /etc/ssl/private/yourdomain.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### Application Security

1. **Environment Variables**: Never hardcode secrets
2. **Secrets Management**: Use HashiCorp Vault, AWS Secrets Manager, or Kubernetes Secrets
3. **Input Validation**: All inputs validated via Pydantic models
4. **Output Sanitization**: Sanitize all user-generated content
5. **CORS**: Restrict to specific origins in production
6. **Authentication**: Implement API key authentication for enterprise clients

### Firewall Rules

```bash
# UFW example
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 443/tcp   # HTTPS
ufw allow 80/tcp    # HTTP (redirect to HTTPS)
ufw enable
```

## Scaling Strategies

### Horizontal Scaling

**Auto-scaling based on metrics**:

```yaml
# Kubernetes Horizontal Pod Autoscaler
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: efficient-ai-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: efficient-ai
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Vertical Scaling

- Monitor CPU/memory utilization
- Increase instance size during peak hours
- Use instance types with burst capability (AWS T-series, Azure B-series)

### Cache Scaling

**Redis Cluster for high throughput**:

```bash
# Redis cluster configuration
redis-server --port 7000 --cluster-enabled yes --cluster-config-file nodes-7000.conf --cluster-node-timeout 5000 --appendonly yes --appendfilename appendonly-7000.aof --dbfilename dump-7000.rdb
```

## High Availability

### Load Balancing

**Multiple load balancer strategies**:

1. **DNS Round Robin**: Simple, no single point of failure
2. **Anycast IP**: Global load balancing (Cloudflare, AWS Route53)
3. **Layer 7 Load Balancer**: Application-aware routing (nginx, HAProxy)

### Database High Availability

**PostgreSQL with streaming replication**:

```sql
-- Primary server configuration
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5

-- Standby server configuration
hot_standby = on
standby_mode = on
primary_conninfo = 'host=primary port=5432 user=replicator password=secret'
```

### Graceful Shutdown

```python
# Handle SIGTERM/SIGINT for zero-downtime deployments
import signal
import asyncio

class GracefulShutdown:
    def __init__(self):
        self.shutdown = False
        
    def signal_handler(self, signum, frame):
        self.shutdown = True
        
    async def wait_for_shutdown(self):
        while not self.shutdown:
            await asyncio.sleep(1)
        # Cleanup: close connections, flush cache, etc.
```

## Monitoring & Observability

### Metrics Collection

**Prometheus configuration**:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'efficient-ai'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

**Key metrics to monitor**:

- Request rate (requests/second)
- Latency (p50, p95, p99)
- Error rate (4xx, 5xx)
- Backend distribution (engine vs ollama vs cloud)
- Cache hit rate
- Payment verification success rate
- GPU utilization (if using Ollama)

### Logging

**Structured logging with ELK stack**:

```python
import structlog

logger = structlog.get_logger()
logger.info("request_processed", 
            tier="engine",
            latency_ms=0.5,
            cost=0.0001,
            user_id="12345")
```

### Alerting

**Alertmanager rules**:

```yaml
groups:
- name: efficient-ai-alerts
  rules:
  - alert: HighErrorRate
    expr: rate(efficient_requests_total{status="error"}[5m]) / rate(efficient_requests_total[5m]) > 0.05
    for: 5m
    annotations:
      summary: "High error rate detected"
  
  - alert: HighLatency
    expr: histogram_quantile(0.95, rate(efficient_request_latency_seconds_bucket[5m])) > 1
    for: 5m
    annotations:
      summary: "95th percentile latency above 1s"
  
  - alert: PaymentVerificationFailure
    expr: rate(efficient_payment_verifications_total{status="failed"}[5m]) > 0.01
    for: 2m
    annotations:
      summary: "Payment verification failing"
  
  - alert: LowCacheHitRate
    expr: efficient_cache_hit_rate < 30
    for: 10m
    annotations:
      summary: "Cache hit rate below 30%"
```

### Prometheus Metrics

The Efficient AI proxy exposes Prometheus metrics at `/metrics`:

**Available Metrics**:

- `efficient_requests_total` - Total requests by tier and status
- `efficient_request_latency_seconds` - Request latency histogram by tier
- `efficient_cache_hit_rate` - Cache hit rate percentage
- `efficient_backend_requests_total` - Requests per backend (engine, ollama, cloud)
- `efficient_payment_verifications_total` - Payment verifications by status
- `efficient_active_requests` - Number of active requests

**Local Setup**:

```bash
# Run Prometheus with the provided config
prometheus --config.file=monitoring/prometheus.yml

# Access metrics
curl http://localhost:8000/metrics
```

**Kubernetes Setup**:

```bash
# Apply ServiceMonitor (requires Prometheus Operator)
kubectl apply -f k8s/servicemonitor.yaml

# Verify metrics are being scraped
kubectl port-forward svc/prometheus-operated 9090:9090
# Open http://localhost:9090/targets
```

### Grafana Dashboard

Import the pre-configured Grafana dashboard:

```bash
# Import dashboard JSON
grafana-cli import monitoring/grafana-dashboard.json
```

**Dashboard Panels**:

1. **Request Rate** - Requests per second by tier and status
2. **Request Latency** - p50, p95, p99 latency by tier
3. **Backend Distribution** - Pie chart of backend usage
4. **Cache Hit Rate** - Gauge showing cache effectiveness
5. **Active Requests** - Current concurrent requests
6. **Payment Verification Success Rate** - Payment success percentage
7. **Error Rate** - Error rate percentage with alerting
8. **Total Requests by Tier** - Request breakdown by tier

## Disaster Recovery

### Backup Strategy

**Daily backups**:

- Database: Daily full backups + WAL archiving
- Cache: Redis persistence (AOF + RDB)
- Configuration: Version control (Git)
- Logs: Centralized log aggregation (ELK, Loki)

**Backup retention**:

- Daily: 7 days
- Weekly: 4 weeks
- Monthly: 12 months

### Recovery Procedures

1. **Database Recovery**:

   ```bash
   # Restore from backup
   pg_restore -d efficient_ai backup.dump
   ```

2. **Cache Recovery**:

   ```bash
   # Redis AOF recovery
   redis-server --appendonly yes --appendfilename appendonly.aof
   ```

3. **Application Recovery**:
   - Deploy from Docker image
   - Restore configuration from secrets manager
   - Verify health endpoints

### Failover Testing

**Monthly failover drills**:

- Simulate primary database failure
- Test load balancer failover
- Verify cache replication
- Test DNS failover

## Compliance

### SOC 2 Type II

**Required controls**:

- Access logging
- Change management
- Incident response procedures
- Data encryption at rest and in transit
- Regular security audits

### GDPR

**Data handling**:

- Data minimization
- Right to deletion
- Data portability
- Consent management
- Data breach notification

### PCI DSS (if handling payment data)

**Requirements**:

- Encryption of payment data
- Secure authentication
- Regular vulnerability scanning
- Network segmentation
- Access control

## Deployment Checklist

### Pre-Deployment

- [ ] Security audit completed
- [ ] Load testing performed
- [ ] Disaster recovery tested
- [ ] Monitoring configured
- [ ] Alerting rules set up
- [ ] SSL certificates obtained
- [ ] DNS records configured
- [ ] Firewall rules applied

### Deployment

- [ ] Database migrations run
- [ ] Configuration deployed
- [ ] Application deployed
- [ ] Health checks passing
- [ ] Smoke tests passed
- [ ] Rollback plan ready

### Post-Deployment

- [ ] Monitoring verified
- [ ] Logs streaming
- [ ] Performance baseline established
- [ ] Team notified
- [ ] Documentation updated

## Support & Maintenance

### SLA Guidelines

|Tier|Uptime|Response Time|Resolution Time|
|------|--------|---------------|-----------------|
|Basic|99.5%|24 hours|72 hours|
|Standard|99.9%|4 hours|24 hours|
|Premium|99.95%|1 hour|4 hours|

### Maintenance Windows

- Scheduled maintenance: Monthly, announced 7 days in advance
- Emergency maintenance: As needed, with immediate notification
- Patch management: Security patches within 48 hours of release

### Upgrade Strategy

1. **Canary Deployment**: Deploy to 10% of instances
2. **Monitor**: Check metrics for 30 minutes
3. **Rollout**: Deploy to remaining instances
4. **Rollback**: Revert if error rate increases > 1%

## Cost Optimization

### Infrastructure Costs

**Estimated monthly costs** (US-East):

|Configuration|Monthly Cost|
|--------------|--------------|
|2x t3.medium + RDS|$150|
|3x m5.large + ElastiCache|$400|
|5x c5.2xlarge + GPU|$1,200|
|Multi-region enterprise|$5,000+|

### Cost Reduction Strategies

1. **Spot Instances**: Use for non-critical workloads (30-70% savings)
2. **Reserved Instances**: Commit to 1-3 years (up to 60% savings)
3. **Auto-scaling**: Scale down during off-peak hours
4. **Cache Optimization**: Increase cache hit rate to reduce backend load
5. **Compression**: Enable gzip compression for API responses

## Troubleshooting

### Common Issues

**High latency**:

- Check cache hit rate
- Verify database query performance
- Monitor GPU utilization (if using Ollama)
- Check network latency to cloud APIs

**Payment verification failures**:

- Verify facilitator URL accessibility
- Check wallet address format
- Verify network configuration (Base vs Solana)
- Check facilitator service status

**High memory usage**:

- Monitor cache size
- Check for memory leaks
- Verify connection pooling
- Review embedding cache size

### Debug Mode

```bash
# Enable debug logging
EFFICIENT_LOG_LEVEL=debug efficient serve --port 8000
```

## Additional Resources

- [x402 Monetization Guide](./X402_MONETIZATION.md)
- [Security Best Practices](./SECURITY.md)
- [Monitoring Guide](./MONITORING.md)
- [API Reference](./API_REFERENCE.md)
