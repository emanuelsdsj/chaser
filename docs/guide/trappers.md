# Trappers

A Trapper is a class that defines two things: **what to fetch** (start URLs and any follow-up requests) and **how to parse** each response (extracting items and new URLs).

## Basic Trapper

```python
from chaser import Item, Request, Trapper


class ArticleItem(Item):
    url: str
    title: str
    body: str


class BlogTrapper(Trapper):
    start_urls = ["https://blog.example.com"]

    async def parse(self, response):
        for link in response.selector.css("article h2 a"):
            yield Request(
                url=response.urljoin(link.attrib["href"]),
                callback="parse_article",
            )

    async def parse_article(self, response):
        yield ArticleItem(
            url=response.url,
            title=response.selector.css("h1::text").get(""),
            body="\n".join(response.selector.css("article p::text").getall()),
        )
```

`callback` routes the response to a different parse method. If omitted, `parse` is called for every response.

## response.follow

`response.follow` and `response.follow_all` are shortcuts for creating requests relative to the current page:

```python
async def parse(self, response):
    # single link from a selector result
    link = response.selector.css("li.next a")
    if link:
        yield response.follow(link)

    # all matching links at once
    yield from response.follow_all(css="div.listing a::attr(href)")
```

## CrawlTrapper

`CrawlTrapper` auto-follows every `<a>` link within `allowed_domains`. Override `parse_item` to extract data from each page — link following is handled for you.

```python
from chaser import CrawlTrapper, Item


class PageItem(Item):
    url: str
    title: str


class SiteCrawler(CrawlTrapper):
    start_urls = ["https://example.com"]
    allowed_domains = ["example.com"]

    # optional: restrict to specific path patterns
    allow_patterns = [r"/blog/", r"/products/"]
    deny_patterns = [r"/admin/", r"\.pdf$"]

    async def parse_item(self, response):
        yield PageItem(
            url=response.url,
            title=response.selector.css("title::text").get(""),
        )
```

| Attribute | Description |
|-----------|-------------|
| `allowed_domains` | Only follow links whose hostname matches one of these |
| `allow_patterns` | Regex list — only follow URLs matching at least one pattern |
| `deny_patterns` | Regex list — never follow URLs matching any pattern |

## SitemapTrapper

`SitemapTrapper` reads `<sitemapindex>` and `<urlset>` XML files and queues every URL it finds. Override `parse_item` to parse individual pages.

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

Nested sitemap indexes are followed recursively.

## Custom settings per Trapper

```python
class MyTrapper(Trapper):
    start_urls = [...]
    custom_settings = {
        "download_delay": 1.0,       # seconds between requests (this trapper only)
        "user_agent": "MyBot/1.0",   # override User-Agent header
    }
```

## Per-request timeout

Pass `meta={"timeout": N}` to override the engine-level timeout for a specific request:

```python
yield Request(url="https://slow.example.com/report", meta={"timeout": 120})
```

## Lifecycle hooks

Override `open` and `close` to manage resources (database connections, files, etc.) that live for the duration of the crawl:

```python
class DbTrapper(Trapper):
    async def open(self):
        self.db = await connect_db()

    async def close(self):
        await self.db.close()

    async def parse(self, response):
        ...
```

## Running multiple Trappers

`Engine.run` accepts a list of Trappers. All share the same connection pool and frontier:

```python
engine = Engine(concurrency=16)
items = await engine.run([BlogTrapper(), ShopTrapper()])
```
