# Configuration

Chaser reads settings from `pyproject.toml` and environment variables. The `Engine` constructor always takes precedence over both — explicit arguments win.

## pyproject.toml

Add a `[tool.chaser]` section to your project's `pyproject.toml`:

```toml
[tool.chaser]
concurrency = 32
download_delay = 0.5
user_agent = "MyBot/1.0 (+https://example.com/bot)"
timeout = 60.0
http2 = true
```

## Environment variables

Every setting can also be set via environment variable with the `CHASER_` prefix:

```bash
CHASER_CONCURRENCY=32
CHASER_DOWNLOAD_DELAY=0.5
CHASER_USER_AGENT="MyBot/1.0"
CHASER_TIMEOUT=60.0
CHASER_HTTP2=true
```

Environment variables override `pyproject.toml`. Engine constructor arguments override both.

## Available settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `concurrency` | `int` | `16` | Number of parallel workers |
| `download_delay` | `float` | `0.0` | Seconds between requests (global) |
| `user_agent` | `str` | httpx default | Default `User-Agent` header |
| `timeout` | `float` | `30.0` | Per-request timeout in seconds |
| `http2` | `bool` | `true` | Enable HTTP/2 |
| `max_connections` | `int` | `100` | Max simultaneous connections in the pool |

## Engine parameters

The `Engine` constructor accepts all settings above plus additional runtime options:

```python
Engine(
    concurrency=16,
    strategy="bfs",        # "bfs", "dfs", or "score"
    http2=True,
    timeout=30.0,
    max_connections=100,
    proxy="socks5://host:1080",   # global proxy for all requests
    hooks=[...],
    retry=RetryPolicy(...),
    pipeline=Pipeline([...]),
    browser=True,          # or BrowserPool(...)
    cache_dir=".cache",
    on_stats=callback,
    stats_interval=60.0,
    frontier_db="crawl.db",
    frontier_redis="redis://localhost:6379",
    metrics=ChaserMetrics(),
    job_name="my_crawl",
)
```

## Logging

Chaser uses Python's standard `logging` module under the `chaser` logger name. To configure it:

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
```

Or from the CLI:

```bash
chaser run mymodule.MyTrapper --log-level DEBUG
chaser run mymodule.MyTrapper --json-logs   # structured JSON output
```
