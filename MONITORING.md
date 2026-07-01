# Monitoring & Observability Guide

Comprehensive monitoring, logging, and observability for Efficient AI in production.

## Table of Contents

- [Overview](#overview)
- [Metrics](#metrics)
- [Logging](#logging)
- [Tracing](#tracing)
- [Alerting](#alerting)
- [Dashboards](#dashboards)
- [Performance Monitoring](#performance-monitoring)
- [Business Metrics](#business-metrics)
- [Tools & Integrations](#tools--integrations)

## Overview

Efficient AI provides observability across three pillars:

1. **Metrics**: Numerical measurements over time (Prometheus, Grafana)
2. **Logs**: Discrete events (ELK, Loki)
3. **Traces**: Request lifecycle across services (OpenTelemetry, Jaeger)

## Metrics

### Core Application Metrics

**Request metrics**:
```python
from prometheus_client import Counter, Histogram, Gauge

# Request counter
request_counter = Counter(
    'efficient_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status', 'tier']
)

# Request latency histogram
request_latency = Histogram(
    'efficient_request_duration_seconds',
    'Request latency in seconds',
    ['endpoint', 'tier'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Active connections gauge
active_connections = Gauge(
    'efficient_active_connections',
    'Number of active connections'
)
```

**Backend distribution metrics**:
```python
backend_requests = Counter(
    'efficient_backend_requests_total',
    'Requests by backend',
    ['backend']  # engine, ollama, cloud, cache
)

backend_latency = Histogram(
    'efficient_backend_duration_seconds',
    'Backend latency in seconds',
    ['backend']
)
```

**Payment metrics**:
```python
payment_requests = Counter(
    'efficient_payment_requests_total',
    'Payment verification requests',
    ['status']  # success, failure, skipped
)

payment_amount = Histogram(
    'efficient_payment_amount_usd',
    'Payment amount in USD',
    buckets=(0.0001, 0.001, 0.01, 0.1, 1.0)
)
```

**Cache metrics**:
```python
cache_hits = Counter('efficient_cache_hits_total', 'Cache hits')
cache_misses = Counter('efficient_cache_misses_total', 'Cache misses')
cache_size = Gauge('efficient_cache_size_bytes', 'Cache size in bytes')
```

### System Metrics

**Resource utilization**:
```python
import psutil

cpu_usage = Gauge('efficient_cpu_usage_percent', 'CPU usage percentage')
memory_usage = Gauge('efficient_memory_usage_bytes', 'Memory usage in bytes')
disk_usage = Gauge('efficient_disk_usage_bytes', 'Disk usage in bytes', ['mount'])

def update_system_metrics():
    cpu_usage.set(psutil.cpu_percent())
    memory_usage.set(psutil.virtual_memory().used)
    disk_usage.labels(mount='/').set(psutil.disk_usage('/').used)
```

**GPU metrics (if using Ollama)**:
```python
import pynvml

pynvml.nvmlInit()
gpu_usage = Gauge('efficient_gpu_usage_percent', 'GPU usage percentage', ['gpu_id'])
gpu_memory = Gauge('efficient_gpu_memory_bytes', 'GPU memory usage', ['gpu_id'])

def update_gpu_metrics():
    device_count = pynvml.nvmlDeviceGetCount()
    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        
        gpu_usage.labels(gpu_id=i).set(utilization.gpu)
        gpu_memory.labels(gpu_id=i).set(memory_info.used)
```

### Prometheus Configuration

**prometheus.yml**:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'efficient-ai'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['localhost:9100']

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['localhost:9121']
```

**Metrics endpoint implementation**:
```python
from prometheus_client import make_asgi_app
from fastapi import FastAPI

app = FastAPI()
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

## Logging

### Structured Logging

**Configuration**:
```python
import structlog
import logging.config

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
})

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
```

**Usage**:
```python
logger.info("request_processed",
            request_id="abc123",
            tier="engine",
            latency_ms=0.5,
            cost=0.0001,
            user_id="user456",
            model="local-engine")

logger.error("payment_verification_failed",
              request_id="abc123",
              error="Invalid signature",
              wallet="0x123...")
```

### Log Levels

| Level | Usage | Example |
|-------|-------|---------|
| DEBUG | Detailed diagnostics | Cache key computation, routing decisions |
| INFO | Normal operations | Request processed, payment verified |
| WARNING | Potentially harmful | High latency, cache miss rate high |
| ERROR | Errors but service continues | Payment verification failed, backend error |
| CRITICAL | Service may be unavailable | Database connection lost, OOM |

### Log Aggregation

**ELK Stack (Elasticsearch, Logstash, Kibana)**:

```yaml
# logstash.conf
input {
  tcp {
    port => 5000
    codec => json_lines
  }
}

filter {
  json {
    source => "message"
  }
  
  if [tier] == "cloud" {
    # Add cloud-specific tags
    mutate { add_field => { "backend_type" => "cloud" } }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "efficient-ai-%{+YYYY.MM.dd}"
  }
}
```

**Loki (lightweight alternative)**:

```yaml
# promtail-config.yml
server:
  http_listen_port: 9080

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: efficient-ai
    static_configs:
      - targets:
          - localhost
        labels:
          job: efficient-ai
          __path__: /var/log/efficient-ai/*.log
```

### Log Retention

**Policy**:
- DEBUG logs: 7 days
- INFO logs: 30 days
- WARNING logs: 90 days
- ERROR logs: 365 days
- CRITICAL logs: 7 years (for compliance)

## Tracing

### OpenTelemetry Integration

**Setup**:
```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure tracing
trace.set_tracer_provider(TracerProvider())
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger",
    agent_port=6831,
)

trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)
```

**Custom spans**:
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def process_request(request_id: str):
    with tracer.start_as_current_span("process_request") as span:
        span.set_attribute("request_id", request_id)
        
        with tracer.start_as_current_span("route_request"):
            tier = route_request(request_id)
            span.set_attribute("tier", tier)
        
        with tracer.start_as_current_span("execute_backend"):
            result = execute_backend(tier)
            span.set_attribute("result", result)
```

### Distributed Tracing Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Load Bal   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────┐
│  Efficient  │────▶│  Redis   │
│     AI      │     └──────────┘
└──────┬──────┘
       │
       ├─────▶ ┌──────────┐
       │      │  Ollama  │
       │      └──────────┘
       │
       └─────▶ ┌──────────┐
              │  Cloud   │
              └──────────┘
```

## Alerting

### Alert Rules

**Prometheus Alertmanager**:

```yaml
groups:
- name: efficient-ai-alerts
  rules:
  # High error rate
  - alert: HighErrorRate
    expr: rate(efficient_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} for the last 5 minutes"

  # High latency
  - alert: HighLatency
    expr: histogram_quantile(0.95, efficient_request_duration_seconds) > 1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "95th percentile latency above 1s"
      description: "P95 latency is {{ $value }}s"

  # Payment verification failures
  - alert: PaymentVerificationFailure
    expr: rate(efficient_payment_requests_total{status="failure"}[5m]) > 0.01
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Payment verification failing"
      description: "Payment failure rate is {{ $value }}"

  # Cache hit rate low
  - alert: LowCacheHitRate
    expr: rate(efficient_cache_hits_total[5m]) / (rate(efficient_cache_hits_total[5m]) + rate(efficient_cache_misses_total[5m])) < 0.3
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Cache hit rate below 30%"
      description: "Cache hit rate is {{ $value }}"

  # High memory usage
  - alert: HighMemoryUsage
    expr: efficient_memory_usage_bytes / efficient_memory_limit_bytes > 0.9
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Memory usage above 90%"
      description: "Memory usage is {{ $value }}"

  # Database connection pool exhausted
  - alert: DatabaseConnectionPoolExhausted
    expr: efficient_db_connections_active / efficient_db_connections_max > 0.9
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Database connection pool nearly exhausted"
      description: "Connection pool usage is {{ $value }}"
```

### Alert Routing

**Alertmanager configuration**:
```yaml
route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

  routes:
  - match:
      severity: critical
    receiver: 'oncall'
    continue: false

  - match:
      severity: warning
    receiver: 'team'
    continue: false

receivers:
- name: 'default'
  email_configs:
  - to: 'team@example.com'

- name: 'oncall'
  pagerduty_configs:
  - service_key: 'YOUR_PAGERDUTY_KEY'
  slack_configs:
  - api_url: 'https://hooks.slack.com/services/...'
    channel: '#alerts-critical'

- name: 'team'
  slack_configs:
  - api_url: 'https://hooks.slack.com/services/...'
    channel: '#alerts'
```

### Alert Severity Levels

| Severity | Response Time | Notification Channels |
|----------|---------------|---------------------|
| Critical | 15 minutes | PagerDuty, Slack, SMS |
| Warning | 1 hour | Slack, Email |
| Info | 24 hours | Email |

## Dashboards

### Grafana Dashboard

**Key panels**:

1. **Request Rate**: Requests per second by tier
2. **Latency**: P50, P95, P99 latency by backend
3. **Error Rate**: 4xx and 5xx error rates
4. **Backend Distribution**: Percentage of requests by backend
5. **Cache Performance**: Hit rate, size, eviction rate
6. **Payment Metrics**: Verification success rate, revenue
7. **Resource Usage**: CPU, memory, GPU utilization
8. **Active Connections**: Current connection count

**Dashboard JSON**:
```json
{
  "dashboard": {
    "title": "Efficient AI Overview",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(efficient_requests_total[1m])",
            "legendFormat": "{{tier}}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "P95 Latency",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, efficient_request_duration_seconds)",
            "legendFormat": "{{tier}}"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

### Business Dashboard

**Revenue tracking**:
```promql
# Total revenue
sum(increase(efficient_payment_amount_usd[1d]))

# Revenue by tier
sum(increase(efficient_payment_amount_usd[1d])) by (tier)

# Revenue trend
sum(increase(efficient_payment_amount_usd[7d]))
```

**Cost savings**:
```promql
# Cloud cost avoided
sum(efficient_backend_requests_total{backend="engine"} or efficient_backend_requests_total{backend="cache"}) * 0.01

# Actual cloud cost
sum(efficient_backend_requests_total{backend="cloud"}) * 0.01
```

## Performance Monitoring

### Apdex Score

**Application Performance Index**:
```python
def calculate_apdex(latencies_ms: list, threshold_ms: float = 500) -> float:
    """
    Apdex = (Satisfied + (Tolerating / 2)) / Total
    - Satisfied: latency <= threshold
    - Tolerating: threshold < latency <= 4 * threshold
    - Frustrated: latency > 4 * threshold
    """
    satisfied = sum(1 for l in latencies_ms if l <= threshold_ms)
    tolerating = sum(1 for l in latencies_ms if threshold_ms < l <= 4 * threshold_ms)
    total = len(latencies_ms)
    
    return (satisfied + (tolerating / 2)) / total if total > 0 else 0
```

### Synthetic Monitoring

**Uptime checks**:
```python
import httpx
import time

async def health_check(url: str) -> dict:
    start = time.time()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}/health", timeout=10.0)
            latency = (time.time() - start) * 1000
            return {
                "status": "up" if response.status_code == 200 else "down",
                "latency_ms": latency,
                "timestamp": time.time()
            }
    except Exception as e:
        return {
            "status": "down",
            "error": str(e),
            "timestamp": time.time()
        }
```

### Real User Monitoring (RUM)

**Client-side metrics**:
```javascript
// Send client-side metrics to server
const metrics = {
  page_load_time: performance.timing.loadEventEnd - performance.timing.navigationStart,
  api_latency: responseTime,
  user_agent: navigator.userAgent,
  timestamp: Date.now()
};

fetch('/api/metrics', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(metrics)
});
```

## Business Metrics

### Key Performance Indicators (KPIs)

| KPI | Formula | Target |
|-----|---------|--------|
| **Request Success Rate** | Successful requests / Total requests | > 99.5% |
| **Average Latency** | Sum of latencies / Request count | < 100ms |
| **Cache Hit Rate** | Cache hits / (Cache hits + misses) | > 40% |
| **Engine Handle Rate** | Engine requests / Total requests | > 80% |
| **Payment Success Rate** | Successful payments / Total payments | > 99% |
| **Cost per 1K Requests** | Total cost / (Requests / 1000) | < $0.50 |
| **Data Center Avoidance** | Non-cloud requests / Total requests | > 90% |

### Revenue Metrics

**Daily revenue**:
```python
def calculate_daily_revenue(date: str) -> float:
    # Query telemetry database
    query = """
    SELECT SUM(cost) as total_revenue
    FROM telemetry
    WHERE DATE(timestamp) = %s
    """
    result = db.execute(query, (date,)).fetchone()
    return result['total_revenue'] or 0.0
```

**Revenue by customer**:
```python
def revenue_by_customer(days: int = 30) -> dict:
    query = """
    SELECT user_id, SUM(cost) as revenue
    FROM telemetry
    WHERE timestamp > NOW() - INTERVAL '%s days'
    GROUP BY user_id
    ORDER BY revenue DESC
    """
    return db.execute(query, (days,)).fetchall()
```

### Usage Analytics

**User engagement**:
```python
def user_engagement_metrics(user_id: str) -> dict:
    query = """
    SELECT 
        COUNT(*) as total_requests,
        COUNT(DISTINCT DATE(timestamp)) as active_days,
        AVG(latency_ms) as avg_latency,
        SUM(cost) as total_spend
    FROM telemetry
    WHERE user_id = %s
    """
    return db.execute(query, (user_id,)).fetchone()
```

## Tools & Integrations

### Recommended Stack

**Open-source**:
- **Metrics**: Prometheus + Grafana
- **Logs**: Loki + Grafana
- **Tracing**: Jaeger + OpenTelemetry
- **Alerting**: Alertmanager

**Cloud-native**:
- **AWS**: CloudWatch + X-Ray + SNS
- **GCP**: Cloud Monitoring + Cloud Trace + Cloud Logging
- **Azure**: Monitor + Application Insights

**SaaS**:
- **Datadog**: All-in-one observability
- **New Relic**: APM + Infrastructure
- **Splunk**: Log analysis + SIEM

### Integration Examples

**Datadog**:
```python
from ddtrace import tracer
from ddtrace.contrib.fastapi import patch as patch_fastapi

patch_fastapi()

@tracer.wrap("process_request")
async def process_request(request):
    # Your code
    pass
```

**CloudWatch**:
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def put_metric(metric_name: str, value: float, dimensions: list):
    cloudwatch.put_metric_data(
        Namespace='EfficientAI',
        MetricData=[{
            'MetricName': metric_name,
            'Value': value,
            'Dimensions': dimensions,
            'Unit': 'Count'
        }]
    )
```

## Monitoring Checklist

### Pre-Production

- [ ] Metrics endpoint configured
- [ ] Structured logging implemented
- [ ] Tracing instrumentation added
- [ ] Alert rules defined
- [ ] Dashboards created
- [ ] Log aggregation configured
- [ ] Retention policies set

### Production

- [ ] All metrics flowing
- [ ] Logs centralized
- [ ] Traces visible
- [ ] Alerts firing correctly
- [ ] Dashboards accurate
- [ ] On-call rotation established
- [ ] Runbooks documented

## Troubleshooting

### Common Issues

**Metrics not appearing**:
- Check Prometheus scrape configuration
- Verify metrics endpoint is accessible
- Check firewall rules

**High latency**:
- Check backend distribution (too many cloud requests?)
- Verify cache hit rate
- Check database query performance
- Monitor network latency

**Alert fatigue**:
- Adjust alert thresholds
- Add alert grouping
- Implement alert suppression during maintenance

## Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Observability Best Practices](https://sre.google/workbook/monitoring-distributed-systems/)
