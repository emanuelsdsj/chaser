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

## Install

```bash
pip install chaser

# with browser support (Playwright)
pip install "chaser[browser]"
playwright install chromium

# with SQLAlchemy store
pip install "chaser[db]"
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
    for item in items:
        print(f"{item.author}: {item.text[:60]}")

asyncio.run(main())
```

## Crawl an entire domain

```python
from chaser import CrawlTrapper, Item


class PageItem(Item):
    url: str
    title: str


class SiteCrawler(CrawlTrapper):
    start_urls = ["https://example.com"]
    allowed_domains = ["example.com"]

    async def parse_item(self, response):
        yield PageItem(
            url=response.url,
            title=response.selector.css("title::text").get(""),
        )
```

`CrawlTrapper` auto-follows every `<a>` link within `allowed_domains`.
Override `parse_item()` to extract data from each page.

## Sitemap-driven crawl

```python
from chaser import Item, SitemapTrapper


class ProductItem(Item):
    url: str
    name: str
    price: str


class ShopTrapper(SitemapTrapper):
    sitemap_urls = ["https://shop.example.com/sitemap.xml"]

    async def parse_item(self, response):
        yield ProductItem(
            url=response.url,
            name=response.selector.css("h1::text").get(""),
            price=response.selector.css(".price::text").get(""),
        )
```

`SitemapTrapper` follows `<sitemapindex>` recursively and extracts `<urlset>` URLs.

## ItemLoader

For pages where extraction needs a bit of cleaning:

```python
from chaser import Item, ItemLoader, compose, first, join, strip


class ArticleItem(Item):
    url: str
    title: str
    body: str
    tags: list[str]


class ArticleTrapper(Trapper):
    start_urls = [...]

    async def parse(self, response):
        loader = ItemLoader(ArticleItem, response=response)
        loader.add_value("url", response.url)
        loader.add_css("title", "h1::text", processor=compose(strip, first()))
        loader.add_css("body", ".content p::text", processor=join("\n"))
        loader.add_css("tags", ".tag::text", processor=strip)
        yield loader.load()
```

## Pipeline and stores

Route items through a processing chain before they're saved:

```python
from chaser import Engine, JsonlStore, Pipeline

pipeline = Pipeline([JsonlStore("output.jsonl")])
engine = Engine(pipeline=pipeline)
await engine.run(MyTrapper())
```

Built-in stores: `JsonlStore`, `CsvStore`, `DbStore` (async SQLAlchemy).

## Hooks

```python
from chaser import CookieJarHook, Engine, RateLimitHook, RetryPolicy

engine = Engine(
    hooks=[
        RateLimitHook(rate=2.0),     # 2 req/s per domain
        CookieJarHook(),             # persist session cookies
    ],
    retry=RetryPolicy(max_retries=3),
)
```

Available hooks: `RateLimitHook`, `CookieJarHook`, `RobotsHook`, `ProxyPool`.

## Browser rendering

For JavaScript-heavy pages, set `use_browser=True` on a request:

```python
from chaser import Engine, Request, Trapper

class JSTrapper(Trapper):
    async def parse(self, response):
        # this response comes from a real Chromium page
        yield ...

    def start_requests(self):
        return [Request(url="https://spa.example.com", use_browser=True)]

engine = Engine(browser=True)
await engine.run(JSTrapper())
```

Requires `pip install "chaser[browser]" && playwright install chromium`.

## Configuration

Settings can live in `pyproject.toml` or environment variables:

```toml
[tool.chaser]
concurrency = 32
download_delay = 0.5
user_agent = "MyBot/1.0"
```

Or via env: `CHASER_CONCURRENCY=32 chaser run mymodule.MyTrapper`.

## CLI

```bash
# run a trapper from the command line
chaser run mymodule.MyTrapper

# interactive shell with a live engine
chaser shell

# version
chaser version
```

## Architecture

```
                    ┌─────────────────────────────────┐
                    │             Engine               │
                    │         (asyncio hub)            │
                    └──┬──────┬──────┬────────┬───────┘
                       │      │      │        │
                  Frontier  Net    Trap    Pipeline
                  (dedup +  Client Layer  (async
                  priority) HTTP/2  parse)  chain)
                       │      │      │        │
                    bloom   conn  Trapper  Pydantic
                   filter   pool callbacks items →
                  + queue  +hooks          store
```

Hub-and-spoke: Engine is the async coordinator, everything else is a spoke.
Not a linear chain — the frontier drives the crawl, the engine dispatches.

## Development

```bash
git clone https://github.com/emanuelsds/chaser
cd chaser
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
pytest
```

## License

MIT
