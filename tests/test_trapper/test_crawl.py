from __future__ import annotations

import pytest

from chaser.item.base import Item
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.crawl import CrawlTrapper


def _response(url: str, body: str, status: int = 200) -> Response:
    req = Request(url=url)
    return Response(
        url=url,
        status=status,
        headers=Headers({"content-type": "text/html; charset=utf-8"}),
        body=body.encode(),
        request=req,
    )


def _html(*hrefs: str) -> str:
    links = "".join(f'<a href="{h}">link</a>' for h in hrefs)
    return f"<html><body>{links}</body></html>"


# ---------------------------------------------------------------------------
# A minimal concrete subclass
# ---------------------------------------------------------------------------


class _SimpleCrawl(CrawlTrapper):
    name = "simple"
    start_urls = ["https://example.com"]
    allowed_domains = ["example.com"]


class _ItemCrawl(CrawlTrapper):
    name = "item"
    start_urls = ["https://example.com"]
    allowed_domains = ["example.com"]

    class PageItem(Item):
        url: str

    async def parse_item(self, response):  # type: ignore[override]
        yield self.PageItem(url=response.url)


# ---------------------------------------------------------------------------
# Tests — link extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follows_absolute_links() -> None:
    resp = _response("https://example.com/", _html("https://example.com/about"))
    results = [r async for r in _SimpleCrawl().parse(resp)]
    urls = [r.url for r in results if isinstance(r, Request)]
    assert "https://example.com/about" in urls


@pytest.mark.asyncio
async def test_follows_relative_links() -> None:
    resp = _response("https://example.com/", _html("/products", "blog/post-1"))
    results = [r async for r in _SimpleCrawl().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://example.com/products" in urls
    assert "https://example.com/blog/post-1" in urls


@pytest.mark.asyncio
async def test_blocks_external_domain() -> None:
    resp = _response(
        "https://example.com/",
        _html("https://evil.com/steal", "https://example.com/safe"),
    )
    results = [r async for r in _SimpleCrawl().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://evil.com/steal" not in urls
    assert "https://example.com/safe" in urls


@pytest.mark.asyncio
async def test_allows_subdomain() -> None:
    trapper = _SimpleCrawl()
    resp = _response(
        "https://example.com/",
        _html("https://shop.example.com/products"),
    )
    results = [r async for r in trapper.parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://shop.example.com/products" in urls


@pytest.mark.asyncio
async def test_skips_denied_extensions() -> None:
    resp = _response(
        "https://example.com/",
        _html(
            "https://example.com/report.pdf",
            "https://example.com/image.jpg",
            "https://example.com/page",
        ),
    )
    results = [r async for r in _SimpleCrawl().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://example.com/report.pdf" not in urls
    assert "https://example.com/image.jpg" not in urls
    assert "https://example.com/page" in urls


@pytest.mark.asyncio
async def test_skips_javascript_and_anchor_hrefs() -> None:
    resp = _response(
        "https://example.com/",
        _html("javascript:void(0)", "#section", "mailto:foo@example.com"),
    )
    results = [r async for r in _SimpleCrawl().parse(resp)]
    requests = [r for r in results if isinstance(r, Request)]
    assert requests == []


@pytest.mark.asyncio
async def test_no_allowed_domains_crawls_everything() -> None:
    class _OpenCrawl(CrawlTrapper):
        name = "open"
        start_urls = ["https://a.com"]

    resp = _response(
        "https://a.com/",
        _html("https://b.com/page", "https://c.com/other"),
    )
    results = [r async for r in _OpenCrawl().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://b.com/page" in urls
    assert "https://c.com/other" in urls


@pytest.mark.asyncio
async def test_parse_item_yields_items() -> None:
    resp = _response("https://example.com/", _html("https://example.com/about"))
    results = [r async for r in _ItemCrawl().parse(resp)]
    items = [r for r in results if isinstance(r, Item)]
    assert len(items) == 1
    assert items[0].url == "https://example.com/"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_default_parse_item_yields_nothing() -> None:
    resp = _response("https://example.com/", "<html></html>")
    results = [r async for r in _SimpleCrawl().parse(resp)]
    items = [r for r in results if isinstance(r, Item)]
    assert items == []


@pytest.mark.asyncio
async def test_meta_carries_trapper_name() -> None:
    resp = _response("https://example.com/", _html("https://example.com/page"))
    results = [r async for r in _SimpleCrawl().parse(resp)]
    requests = [r for r in results if isinstance(r, Request)]
    for req in requests:
        assert req.meta.get("trapper") == "simple"


# ---------------------------------------------------------------------------
# Tests — depth_limit
# ---------------------------------------------------------------------------


def _response_at_depth(url: str, body: str, depth: int) -> Response:
    req = Request(url=url, meta={"depth": depth})
    return Response(
        url=url,
        status=200,
        headers=Headers({"content-type": "text/html; charset=utf-8"}),
        body=body.encode(),
        request=req,
    )


@pytest.mark.asyncio
async def test_depth_limit_stops_following_links() -> None:
    class _LimitedCrawl(CrawlTrapper):
        name = "limited"
        start_urls = ["https://example.com"]
        depth_limit = 1

    resp = _response_at_depth("https://example.com/", _html("https://example.com/page"), depth=1)
    results = [r async for r in _LimitedCrawl().parse(resp)]
    requests = [r for r in results if isinstance(r, Request)]
    assert requests == []


@pytest.mark.asyncio
async def test_depth_limit_none_follows_all() -> None:
    resp = _response_at_depth("https://example.com/", _html("https://example.com/page"), depth=100)
    results = [r async for r in _SimpleCrawl().parse(resp)]
    requests = [r for r in results if isinstance(r, Request)]
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_depth_propagates_in_meta() -> None:
    resp = _response_at_depth("https://example.com/", _html("https://example.com/p1"), depth=2)
    results = [r async for r in _SimpleCrawl().parse(resp)]
    requests = [r for r in results if isinstance(r, Request)]
    assert len(requests) == 1
    assert requests[0].meta["depth"] == 3


@pytest.mark.asyncio
async def test_depth_limit_items_still_yielded() -> None:
    """Items are yielded even when depth limit is reached — only link following stops."""

    class _LimitedItem(CrawlTrapper):
        name = "limiteditem"
        start_urls = ["https://example.com"]
        depth_limit = 0

        class Page(Item):
            url: str

        async def parse_item(self, response):  # type: ignore[override]
            yield self.Page(url=response.url)

    resp = _response_at_depth("https://example.com/", _html("https://example.com/p"), depth=0)
    results = [r async for r in _LimitedItem().parse(resp)]
    items = [r for r in results if isinstance(r, Item)]
    requests = [r for r in results if isinstance(r, Request)]
    assert len(items) == 1
    assert requests == []
