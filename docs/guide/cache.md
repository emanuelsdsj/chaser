# HTTP Cache

Chaser can cache responses to disk and skip re-fetching pages that have not changed. This speeds up iterative development (run your parser repeatedly without hammering the server) and makes partial-failure recovery cheaper.

## Enable caching

```python
engine = Engine(cache_dir=".cache")
await engine.run(MyTrapper())
```

The first run fetches everything and writes responses to `.cache/`. Subsequent runs serve cached responses instantly for anything that is still fresh.

## Cache behaviour

Chaser implements standard HTTP cache semantics:

| Header | Behaviour |
|--------|-----------|
| `Cache-Control: max-age=N` | Cache for N seconds |
| `Cache-Control: no-store` | Never cache |
| `ETag` / `If-None-Match` | Conditional GET — 304 responses served from cache |
| `Last-Modified` / `If-Modified-Since` | Conditional GET — 304 responses served from cache |

Responses without any caching headers are cached for the session (never re-validated during the same run, always re-fetched on the next run).

## Cache hits in stats

`engine.stats.cache_hits` counts how many responses were served from the cache:

```python
items = await engine.run(MyTrapper())
print(f"Fetched: {engine.stats.requests_ok}, cached: {engine.stats.cache_hits}")
```

## Cache directory layout

Each response is stored as two files under `cache_dir/`:

```
.cache/
├── abc123.body      # raw response bytes
└── abc123.meta      # URL, status, headers, timestamp (JSON)
```

The filename is derived from the canonical URL. It is safe to delete individual files or the entire directory at any time.

## Development workflow

A typical development cycle with caching:

```bash
# first run — fetches everything, populates the cache
python run.py

# subsequent runs — parses from cache, no network traffic
python run.py
python run.py

# reset cache when you want fresh data
rm -rf .cache/
python run.py
```
