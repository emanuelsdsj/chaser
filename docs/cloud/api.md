# REST API

The Chaser API server manages crawl jobs over HTTP. Start it, submit Trapper classes by dotted path, and poll for status and items — all from curl, a browser, or any HTTP client.

## Setup

```bash
pip install "chaser[api]"
chaser serve
```

The server starts on `http://localhost:8000` by default. Port can be changed:

```bash
chaser serve --port 9000
```

## Endpoints

### Start a crawl

```
POST /crawls
```

```bash
curl -X POST http://localhost:8000/crawls \
  -H "Content-Type: application/json" \
  -d '{
    "trapper": "mymodule.trappers.QuoteTrapper",
    "concurrency": 8
  }'
```

**Request body**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `trapper` | `string` | required | Dotted import path to the Trapper class |
| `concurrency` | `int` | `16` | Number of parallel workers |
| `http2` | `bool` | `true` | Enable HTTP/2 |
| `timeout` | `float` | `30.0` | Per-request timeout in seconds |
| `proxy` | `string` | `null` | Proxy URL for all requests |
| `cache_dir` | `string` | `null` | Path to HTTP cache directory |
| `frontier_db` | `string` | `null` | Path to SQLite frontier for resume |

**Response** — `201 Created`

```json
{
  "id": "a1b2c3d4",
  "status": "running",
  "trapper": "mymodule.trappers.QuoteTrapper",
  "stats": { "requests_sent": 0, "items_scraped": 0, ... },
  "items_count": 0,
  "error": null
}
```

### List all jobs

```
GET /crawls
```

Returns an array of all jobs (running, finished, failed).

### Get a job

```
GET /crawls/{id}
```

```bash
curl http://localhost:8000/crawls/a1b2c3d4
```

`status` is one of `running`, `finished`, or `failed`.

### Cancel a job

```
DELETE /crawls/{id}
```

Cancels the asyncio task. Already-collected items are preserved.

### Get items

```
GET /crawls/{id}/items?offset=0&limit=100
```

Returns paginated items collected so far. Available while the job is still running.

```bash
curl "http://localhost:8000/crawls/a1b2c3d4/items?limit=50"
```

## Stats fields

The `stats` object in every response:

| Field | Description |
|-------|-------------|
| `requests_sent` | Total requests dispatched |
| `requests_ok` | Successful responses (2xx) |
| `requests_failed` | Failed requests (error or 4xx/5xx) |
| `cache_hits` | Responses served from HTTP cache |
| `items_scraped` | Items yielded by Trappers |
| `bytes_downloaded` | Total bytes received |
| `timeouts` | Requests that timed out |
| `errors_by_status` | Dict of HTTP status code → count |
| `elapsed` | Seconds since the job started |
| `requests_per_second` | Throughput over `elapsed` |

## Interactive docs

The API server exposes Swagger UI at `http://localhost:8000/docs` and ReDoc at `http://localhost:8000/redoc`.

## Prometheus metrics

When `chaser[metrics]` is also installed, the server exposes a `/metrics` endpoint in Prometheus text format. See [Prometheus Metrics](metrics.md) for details.
