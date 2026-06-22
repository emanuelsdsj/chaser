# Hooks

Hooks intercept every request and response passing through the Net Client. They run before a request is sent (`before_request`) and after a response arrives (`after_response`). Multiple hooks are chained in the order they are passed to the Engine.

```python
from chaser import CookieJarHook, Engine, RateLimitHook, RetryPolicy

engine = Engine(
    hooks=[
        RateLimitHook(rate=2.0),
        CookieJarHook(),
    ],
    retry=RetryPolicy(max_retries=3),
)
```

## RateLimitHook

Per-domain token bucket. Each domain gets an independent bucket — throttling one domain never slows another.

```python
from chaser import RateLimitHook

RateLimitHook(rate=1.0)   # 1 request/second per domain (default)
RateLimitHook(rate=5.0, burst=10)  # allow short bursts up to 10
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `rate` | `1.0` | Sustained requests per second per domain |
| `burst` | `1` | Maximum token headroom — controls burst size |

## RetryPolicy

Exponential backoff with full jitter for transport-level failures (connection errors, timeouts). HTTP 4xx/5xx responses are not retried — that's application logic.

```python
from chaser import RetryPolicy

RetryPolicy(
    max_retries=3,      # retries after the first attempt
    base_delay=1.0,     # wait before attempt 1 (doubles each retry)
    max_delay=60.0,     # cap on computed delay before jitter
    jitter=True,        # multiply by uniform(0.5, 1.5)
)
```

Delay formula: `min(base_delay × 2^attempt, max_delay) × uniform(0.5, 1.5)`

## CookieJarHook

Maintains a cookie jar per domain. Cookies received in `Set-Cookie` response headers are automatically sent with subsequent requests to the same domain.

```python
from chaser import CookieJarHook

CookieJarHook()
```

No configuration needed. Useful for sites that require a session cookie before they serve content.

## RobotsHook

Fetches and caches `robots.txt` for each domain. Requests to disallowed paths are aborted before they are sent.

```python
from chaser import RobotsHook

engine = Engine(hooks=[RobotsHook()])
```

## ProxyPool

Rotates through a list of proxy URLs. On each request, the next proxy in the pool is selected round-robin. Failed proxies can be marked unhealthy automatically.

```python
from chaser import ProxyPool

proxies = ProxyPool([
    "http://proxy1:8080",
    "http://proxy2:8080",
    "socks5://proxy3:1080",
])
engine = Engine(hooks=[proxies])
```

## BandwidthThrottleHook

Limits download speed across all concurrent workers. Useful when you need to cap bandwidth consumption on a shared connection.

```python
from chaser.hooks.bandwidth import BandwidthThrottleHook

engine = Engine(hooks=[BandwidthThrottleHook(max_mbps=10.0)])
```

## AutoThrottleHook

Adjusts request rate dynamically based on server response latency. Backs off when the server is slow, speeds up when it is fast.

```python
from chaser import AutoThrottleHook

engine = Engine(hooks=[AutoThrottleHook(target_latency=1.0, max_rate=10.0)])
```

## HarWriter

Records every request and response in [HAR 1.2](https://www.softwareishard.com/blog/har-12-spec/) format. Useful for debugging and replay.

```python
from chaser import Engine, HarWriter

async with HarWriter("crawl.har") as har:
    engine = Engine(hooks=[har])
    await engine.run(MyTrapper())
# crawl.har is flushed and closed automatically on exit
```

## Writing a custom hook

Implement the `FetchHook` protocol — one or both methods:

```python
from chaser.hooks.base import FetchHook
from chaser.net.request import Request
from chaser.net.response import Response


class TimingHook(FetchHook):
    async def before_request(self, request: Request) -> Request:
        # modify the request or just observe it; must return a Request
        return request

    async def after_response(self, response: Response) -> Response:
        print(f"{response.url} — {response.elapsed:.3f}s")
        return response
```

To abort a request from `before_request`, raise `RequestAborted`:

```python
from chaser.hooks.base import FetchHook, RequestAborted

class BlocklistHook(FetchHook):
    def __init__(self, blocked: set[str]) -> None:
        self._blocked = blocked

    async def before_request(self, request: Request) -> Request:
        from urllib.parse import urlparse
        if urlparse(request.url).netloc in self._blocked:
            raise RequestAborted(f"Blocked: {request.url}")
        return request
```
