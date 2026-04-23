# Net Layer

The `chaser.net` package is the foundation of every crawl — it defines how requests
are described and how responses are represented.

## Request

`Request` is a dataclass that describes a single fetch operation.

```python
from chaser.net.request import Request

req = Request(url="https://example.com")
req = Request(
    url="https://example.com/login",
    method="POST",
    headers={"Content-Type": "application/json"},
    body=b'{"user": "me"}',
    meta={"source": "seed"},
    priority=10,
    callback="parse_login",
    use_browser=False,
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | — | Target URL |
| `method` | `str` | `"GET"` | HTTP method (auto-uppercased) |
| `headers` | `Headers` | `{}` | Request headers |
| `body` | `bytes \| None` | `None` | Request body |
| `meta` | `dict` | `{}` | Arbitrary data passed through to the response |
| `priority` | `int` | `0` | Higher = fetched sooner |
| `callback` | `str \| None` | `None` | Trapper method name to call with the response |
| `use_browser` | `bool` | `False` | Route to Playwright instead of httpx |

Use `request.copy(**overrides)` to produce a modified copy without mutating the original.

## Response

`Response` wraps the raw HTTP response with convenient accessors.

```python
from chaser.net.response import Response
from chaser.net.headers import Headers

res = Response(
    url="https://example.com",
    status=200,
    headers=Headers({"content-type": "text/html"}),
    body=b"<html>...</html>",
    elapsed=0.34,
)

print(res.text)      # decoded string
print(res.ok)        # True if 200–299
print(res.json())    # parsed JSON (raises if not JSON)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | — | Final URL after redirects |
| `status` | `int` | — | HTTP status code |
| `headers` | `Headers` | — | Response headers |
| `body` | `bytes` | — | Raw response body |
| `encoding` | `str` | `"utf-8"` | Charset for `.text` decoding |
| `elapsed` | `float` | `0.0` | Seconds taken to fetch |
| `request` | `Request \| None` | `None` | The request that produced this response |

`.css()` and `.xpath()` shortcuts are added in the `extract` phase.

## Headers

`Headers` is a case-insensitive dict. `"Content-Type"` and `"content-type"` are the same key.

```python
from chaser.net.headers import Headers

h = Headers({"Content-Type": "text/html", "X-Custom": "value"})
assert h["content-type"] == "text/html"
assert "CONTENT-TYPE" in h
```
