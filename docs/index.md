# Chaser

A fast, reliable web crawling framework built on modern Python asyncio.

HTTP/2 by default. Pydantic-validated items. Bloom filter dedup.
No legacy event loop libraries — just plain asyncio.

---

## Why Chaser

Most Python crawling tools were designed before modern asyncio existed. They work, but they carry historical baggage: legacy async runtimes, no type hints, items that are basically untyped dicts, and dedup that eats RAM on large crawls.

Chaser is a clean rewrite with none of that baggage:

- **HTTP/2 by default** — multiplexed connections via httpx, lower latency per domain
- **Typed items** — define your schema with Pydantic; invalid data never reaches your store
- **Bloom filter dedup** — O(1) memory per URL regardless of crawl size
- **Pure asyncio** — no Twisted, no greenlets, no legacy runtime to learn

## Install

```bash
pip install chaser
```

With optional extras:

```bash
pip install "chaser[browser]"    # Playwright for JS-heavy pages
pip install "chaser[api]"        # REST API server
pip install "chaser[metrics]"    # Prometheus metrics
pip install "chaser[db]"         # async SQLAlchemy store
pip install "chaser[redis]"      # distributed Redis frontier
pip install "chaser[parquet]"    # Parquet output via pyarrow
pip install "chaser[cloud]"      # S3 and GCS stores
```

## Quick start

```python
import asyncio
from chaser import Engine, Item, Request, Trapper


class QuoteItem(Item):
    text: str
    author: str


class QuoteTrapper(Trapper):
    start_urls = ["https://quotes.toscrape.com"]

    async def parse(self, response):
        for quote in response.selector.css("div.quote"):
            yield QuoteItem(
                text=quote.css("span.text::text").get(""),
                author=quote.css("small.author::text").get(""),
            )

        next_page = response.selector.css("li.next a::attr(href)").get()
        if next_page:
            yield Request(url=response.urljoin(next_page))


async def main():
    engine = Engine(concurrency=4)
    items = await engine.run(QuoteTrapper())
    print(engine.stats)

asyncio.run(main())
```

That's it. No configuration files required, no class registration, no framework ceremony.

## What's next

- [Getting Started](getting-started.md) — a full walk-through from install to first crawl
- [Trappers](guide/trappers.md) — define what to fetch and how to parse it
- [Pipeline & Stores](guide/pipeline.md) — route items to JSONL, CSV, S3, GCS, or a database
- [Hooks](guide/hooks.md) — rate limiting, retries, proxies, robots.txt
- [Browser Rendering](guide/browser.md) — scrape JavaScript-heavy pages with Playwright
