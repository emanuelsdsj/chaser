from __future__ import annotations

import pytest

from chaser.item.base import Item
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.sitemap import SitemapTrapper

_XML_CT = {"content-type": "application/xml"}
_HTML_CT = {"content-type": "text/html; charset=utf-8"}

_SITEMAP_INDEX = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-blog.xml</loc></sitemap>
</sitemapindex>
"""

_SITEMAP_URLSET = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page-1</loc></url>
  <url><loc>https://example.com/page-2</loc></url>
</urlset>
"""


def _sitemap_response(url: str, body: bytes) -> Response:
    req = Request(url=url, meta={"is_sitemap": True})
    return Response(
        url=url,
        status=200,
        headers=Headers(_XML_CT),
        body=body,
        request=req,
    )


def _page_response(url: str) -> Response:
    req = Request(url=url)
    return Response(
        url=url,
        status=200,
        headers=Headers(_HTML_CT),
        body=b"<html><body><h1>Hello</h1></body></html>",
        request=req,
    )


# ---------------------------------------------------------------------------
# Concrete subclass used across tests
# ---------------------------------------------------------------------------


class _ShopTrapper(SitemapTrapper):
    name = "shop"
    sitemap_urls = ["https://example.com/sitemap.xml"]

    class ProductItem(Item):
        url: str

    async def parse_item(self, response):  # type: ignore[override]
        yield self.ProductItem(url=response.url)


# ---------------------------------------------------------------------------
# Tests — start_requests
# ---------------------------------------------------------------------------


def test_start_requests_from_sitemap_urls() -> None:
    t = _ShopTrapper()
    reqs = t.start_requests()
    assert len(reqs) == 1
    assert reqs[0].url == "https://example.com/sitemap.xml"
    assert reqs[0].meta["is_sitemap"] is True


def test_start_requests_derived_from_start_urls() -> None:
    class _T(SitemapTrapper):
        name = "t"
        start_urls = ["https://example.com/blog", "https://example.com/shop"]

    reqs = _T().start_requests()
    assert len(reqs) == 1  # same domain → deduped
    assert reqs[0].url == "https://example.com/sitemap.xml"


def test_start_requests_multiple_domains() -> None:
    class _T(SitemapTrapper):
        name = "t"
        start_urls = ["https://a.com/", "https://b.com/"]

    reqs = _T().start_requests()
    urls = {r.url for r in reqs}
    assert "https://a.com/sitemap.xml" in urls
    assert "https://b.com/sitemap.xml" in urls


# ---------------------------------------------------------------------------
# Tests — sitemap parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parses_sitemap_index() -> None:
    resp = _sitemap_response("https://example.com/sitemap.xml", _SITEMAP_INDEX)
    results = [r async for r in _ShopTrapper().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://example.com/sitemap-pages.xml" in urls
    assert "https://example.com/sitemap-blog.xml" in urls


@pytest.mark.asyncio
async def test_sitemap_index_requests_are_marked() -> None:
    resp = _sitemap_response("https://example.com/sitemap.xml", _SITEMAP_INDEX)
    results = [r async for r in _ShopTrapper().parse(resp)]
    for req in results:
        assert req.meta.get("is_sitemap") is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_parses_urlset() -> None:
    resp = _sitemap_response("https://example.com/sitemap-pages.xml", _SITEMAP_URLSET)
    results = [r async for r in _ShopTrapper().parse(resp)]
    urls = {r.url for r in results if isinstance(r, Request)}
    assert "https://example.com/page-1" in urls
    assert "https://example.com/page-2" in urls


@pytest.mark.asyncio
async def test_urlset_requests_not_marked_as_sitemap() -> None:
    resp = _sitemap_response("https://example.com/sitemap-pages.xml", _SITEMAP_URLSET)
    results = [r async for r in _ShopTrapper().parse(resp)]
    for req in results:
        assert not req.meta.get("is_sitemap")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_bad_xml_silently_skipped() -> None:
    resp = _sitemap_response("https://example.com/sitemap.xml", b"not xml at all!!!")
    results = [r async for r in _ShopTrapper().parse(resp)]
    assert results == []


@pytest.mark.asyncio
async def test_parse_item_called_for_non_sitemap() -> None:
    resp = _page_response("https://example.com/page-1")
    results = [r async for r in _ShopTrapper().parse(resp)]
    items = [r for r in results if isinstance(r, Item)]
    assert len(items) == 1
    assert items[0].url == "https://example.com/page-1"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_default_parse_item_yields_nothing() -> None:
    class _Plain(SitemapTrapper):
        name = "plain"
        sitemap_urls = ["https://example.com/sitemap.xml"]

    resp = _page_response("https://example.com/page")
    results = [r async for r in _Plain().parse(resp)]
    items = [r for r in results if isinstance(r, Item)]
    assert items == []
