# Getting Started

## Installation

```bash
pip install chaser
```

Python 3.11 or higher is required.

## Your first Trapper

A **Trapper** is a class that tells Chaser what to fetch and how to parse it. Define one by subclassing `Trapper`, setting `start_urls`, and writing a `parse` method that yields items and follow-up requests.

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
    for item in items:
        print(f"{item.author}: {item.text[:60]}")
    print(engine.stats)


asyncio.run(main())
```

### What's happening here

1. `QuoteItem` defines the data schema — any item that doesn't match the types raises a `ValidationError` before it reaches your store.
2. `QuoteTrapper.parse` uses CSS selectors (via `response.selector`) to extract data and yields `QuoteItem` objects.
3. Yielding a `Request` re-enqueues a URL back into the Frontier; Chaser deduplicates it automatically using a bloom filter.
4. `Engine(concurrency=4)` runs 4 workers in parallel, sharing a single connection pool.

## Run from the CLI

Save your Trapper to `myproject/trappers.py` and run it:

```bash
chaser run myproject.trappers.QuoteTrapper
```

Or scaffold a complete project first:

```bash
chaser new myproject
cd myproject
chaser run myproject.trappers.QuoteTrapper
```

## Saving items to a file

By default `engine.run()` collects items in memory and returns them. To stream to disk instead, attach a pipeline:

```python
from chaser import Engine, JsonlStore, Pipeline

pipeline = Pipeline([JsonlStore("quotes.jsonl")])
engine = Engine(pipeline=pipeline)
await engine.run(QuoteTrapper())
```

Items are written to `quotes.jsonl` as they arrive — no buffering in memory.

## What to read next

| Goal | Guide |
|------|-------|
| Crawl an entire domain | [Trappers — CrawlTrapper](guide/trappers.md#crawltrapper) |
| Validate and transform items | [Items & Loaders](guide/items.md) |
| Store to CSV, database, S3 | [Pipeline & Stores](guide/pipeline.md) |
| Rate limiting, retries, proxies | [Hooks](guide/hooks.md) |
| Scrape JavaScript pages | [Browser Rendering](guide/browser.md) |
| Resume a crashed crawl | [Crawl Resume](guide/resume.md) |
