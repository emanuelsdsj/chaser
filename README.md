# chaser

A web crawling and data extraction framework built on modern Python asyncio.

HTTP/2 by default. Pydantic-validated items. Bloom filter dedup.
No legacy event loop libraries — just plain asyncio.

---

## Why

Most Python crawling tools were designed before modern asyncio existed.
They work, but they carry a lot of historical baggage: legacy async runtimes,
no type hints, items that are basically untyped dicts, and dedup that eats RAM
on large crawls.

Chaser is a clean rewrite with none of that baggage.

## Status

Early development. Not ready for production use yet.

## Architecture

```
Engine (asyncio hub)
├── Frontier     bloom filter dedup + priority queue
├── Fetcher      httpx, HTTP/2, circuit breaker, SOCKS5
├── Trap Layer   isolated trapper execution
└── Pipeline     Pydantic items → validate → export
```

The key concept is the **Trapper** — a class that defines what to fetch
and how to parse it. Think of it as a self-contained crawl job.

## Quick start

```python
# not ready yet — check back soon
```

## Install

```bash
pip install chaser
```

## Development setup

```bash
git clone https://github.com/emanuelsds/chaser
cd chaser
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Running tests

```bash
pytest
```

## License

MIT
