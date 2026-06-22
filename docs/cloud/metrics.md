# Prometheus Metrics

Chaser exposes crawl metrics in standard Prometheus text format. Every metric is tagged with a `job` label so multiple concurrent crawls are tracked without collision.

## Setup

```bash
pip install "chaser[api,metrics]"
chaser serve
```

Metrics are available at:

```
GET http://localhost:8000/metrics
```

## Available metrics

| Metric | Type | Description |
|--------|------|-------------|
| `chaser_requests_total` | Counter | Total requests by result (`ok`, `timeout`, `failed`, `circuit_open`, `aborted`, `cached`) |
| `chaser_items_scraped_total` | Counter | Items yielded by Trappers |
| `chaser_bytes_downloaded_total` | Counter | Raw bytes received from servers |
| `chaser_request_duration_seconds_p99` | Gauge | 99th percentile request latency |
| `chaser_frontier_queue_size` | Gauge | Current pending URL count |
| `chaser_frontier_seen_urls` | Gauge | Total distinct URLs seen |
| `chaser_http_errors_total` | Counter | HTTP error responses by status code |

All metrics carry a `job` label matching the `job_name` passed to the Engine.

## Example output

```
# HELP chaser_requests_total Total requests dispatched
# TYPE chaser_requests_total counter
chaser_requests_total{job="product_crawl", result="ok"} 1423.0
chaser_requests_total{job="product_crawl", result="timeout"} 3.0

# HELP chaser_items_scraped_total Total items scraped
# TYPE chaser_items_scraped_total counter
chaser_items_scraped_total{job="product_crawl"} 891.0

# HELP chaser_bytes_downloaded_total Total bytes downloaded
# TYPE chaser_bytes_downloaded_total counter
chaser_bytes_downloaded_total{job="product_crawl"} 8473291.0

# HELP chaser_frontier_queue_size Current frontier queue size
# TYPE chaser_frontier_queue_size gauge
chaser_frontier_queue_size{job="product_crawl"} 342.0

# HELP chaser_http_errors_total HTTP error responses by status code
# TYPE chaser_http_errors_total counter
chaser_http_errors_total{job="product_crawl", status_code="429"} 18.0
```

## Standalone mode (without the API server)

Use `ChaserMetrics` directly in a script:

```python
import asyncio
from chaser import Engine
from chaser.metrics import ChaserMetrics

metrics = ChaserMetrics()
engine = Engine(metrics=metrics, job_name="product_crawl")
await engine.run(MyTrapper())
```

In standalone mode, metrics accumulate in memory. Expose them with the built-in ASGI app if you want to scrape them:

```python
import uvicorn
from chaser.metrics import ChaserMetrics

metrics = ChaserMetrics()
app = metrics.make_asgi_app()
uvicorn.run(app, host="0.0.0.0", port=9090)
```

## Grafana dashboard

A minimal Grafana dashboard can be built from these series. Recommended panels:

- **Throughput**: rate of `chaser_requests_total{result="ok"}` over 1m
- **Error rate**: rate of `chaser_http_errors_total` over 1m
- **Queue depth**: `chaser_frontier_queue_size` — dropping to 0 means the crawl is finishing
- **Latency p99**: `chaser_request_duration_seconds_p99`
- **Items/s**: rate of `chaser_items_scraped_total` over 1m
