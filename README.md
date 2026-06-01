# chaser

A web crawling and data extraction framework built on modern Python asyncio.

HTTP/2 by default. Pydantic-validated items. Bloom filter dedup.
No legacy event loop libraries, just plain asyncio.

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

# with REST API and process management
pip install "chaser[api]"

# with Prometheus metrics
pip install "chaser[metrics]"

# with SQLAlchemy store
pip install "chaser[db]"

# everything
pip install "chaser[browser,api,metrics,db]"
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

Route items through a processing chain before they are saved:

```python
from chaser import Engine, JsonlStore, Pipeline
from chaser.pipeline.filters import DuplicateFilter

pipeline = Pipeline(
    [
        DuplicateFilter(key=lambda i: i.url),
        JsonlStore("output.jsonl"),
    ],
    dead_letter="failed.jsonl",
)
engine = Engine(pipeline=pipeline)
await engine.run(MyTrapper())
```

`DuplicateFilter` drops items whose key has already been seen. `dead_letter` captures
anything that raises an exception in any stage so nothing is silently lost.

Built-in stores: `JsonlStore`, `CsvStore`, `DbStore` (async SQLAlchemy).

## Crawl resume

Long crawls crash. The SQLite frontier persists state to disk so you can pick
up exactly where things stopped:

```python
engine = Engine(frontier_db="crawl.db")
await engine.run(MyTrapper())
```

On the next run with the same `frontier_db` path, already-seen URLs are skipped
and the pending queue is restored. Requests that were in-flight when the process
died are moved back to pending automatically.

## HTTP cache

Avoid re-fetching pages that have not changed. Chaser respects `Cache-Control`,
`ETag`, and `Last-Modified` headers and stores responses on disk:

```python
engine = Engine(cache_dir=".cache")
await engine.run(MyTrapper())
```

Second run is instant for anything the server says is still fresh.

## Live stats

Get a snapshot of what is happening every N seconds while the crawl runs:

```python
def on_stats(stats):
    print(f"  {stats.requests_sent} req sent, {stats.items_scraped} items")

engine = Engine(on_stats=on_stats, stats_interval=10.0)
await engine.run(MyTrapper())
```

## Hooks

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

Available hooks: `RateLimitHook`, `CookieJarHook`, `RobotsHook`, `ProxyPool`.

## Browser rendering

For JavaScript-heavy pages, set `use_browser=True` on a request:

```python
from chaser import Engine, Request, Trapper

class JSTrapper(Trapper):
    async def parse(self, response):
        yield ...

    def start_requests(self):
        return [Request(url="https://spa.example.com", use_browser=True)]

engine = Engine(browser=True)
await engine.run(JSTrapper())
```

Requires `pip install "chaser[browser]" && playwright install chromium`.

The browser pool reuses Playwright pages across requests instead of opening and
closing a full browser context for each URL, which makes it substantially faster
on crawls with many browser requests.

## REST API

Start a long-running API server to manage and monitor crawl jobs over HTTP:

```bash
pip install "chaser[api]"
chaser serve
```

```
POST   /crawls              start a crawl job in the background
GET    /crawls              list all jobs with current stats
GET    /crawls/{id}         status, stats, error for a specific job
DELETE /crawls/{id}         cancel a running job
GET    /crawls/{id}/items   paginated items collected so far
```

Start a crawl:

```bash
curl -X POST http://localhost:8000/crawls \
  -H "Content-Type: application/json" \
  -d '{"trapper": "mymodule:MyTrapper", "concurrency": 8}'
```

Poll it:

```bash
curl http://localhost:8000/crawls/a1b2c3d4
```

## Prometheus metrics

Chaser exposes a `/metrics` endpoint in standard Prometheus text format when
`chaser[metrics]` is installed alongside `chaser[api]`:

```bash
pip install "chaser[api,metrics]"
chaser serve
curl http://localhost:8000/metrics
```

Every crawl job gets its own `job` label so multiple concurrent crawls are
tracked without collision:

```
chaser_requests_total{job="a1b2c3d4", result="ok"} 1423
chaser_requests_total{job="a1b2c3d4", result="timeout"} 3
chaser_items_scraped_total{job="a1b2c3d4"} 891
chaser_bytes_downloaded_total{job="a1b2c3d4"} 8473291
chaser_request_duration_seconds_p99{job="a1b2c3d4"} 1.23
chaser_frontier_queue_size{job="a1b2c3d4"} 342
chaser_http_errors_total{job="a1b2c3d4", status_code="429"} 18
```

You can also use metrics in standalone mode without the API:

```python
from chaser import Engine
from chaser.metrics import ChaserMetrics

metrics = ChaserMetrics()
engine = Engine(metrics=metrics, job_name="product_crawl")
await engine.run(MyTrapper())
```

## Testing your trappers

```python
from chaser.testing import FakeResponse, assert_items

async def test_quote_trapper():
    html = """
        <div class="quote">
            <span class="text">The only way out is through.</span>
            <small class="author">Robert Frost</small>
        </div>
    """
    response = FakeResponse(url="https://quotes.toscrape.com", html=html)
    await assert_items(QuoteTrapper(), response, [
        QuoteItem(text="The only way out is through.", author="Robert Frost"),
    ])
```

No real HTTP needed, no mocking setup, just a `FakeResponse`.

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
# scaffold a new project
chaser new myproject

# run a trapper
chaser run mymodule.MyTrapper

# start the REST API server
chaser serve

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
                  (dedup +  Client layer  (async
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
