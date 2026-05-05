from __future__ import annotations

import pytest

from chaser.item.base import Item
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.testing import FakeResponse, assert_items, collect_parse
from chaser.trapper.base import Trapper

# ---------------------------------------------------------------------------
# Minimal trappers for testing
# ---------------------------------------------------------------------------


class _TitleItem(Item):
    url: str
    title: str


class _TitleTrapper(Trapper):
    name = "title"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        title = response.selector.css("h1::text").get("no title")
        yield _TitleItem(url=response.url, title=title)


class _LinkTrapper(Trapper):
    name = "link"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        for href in response.selector.css("a::attr(href)").getall():
            yield Request(url=response.urljoin(href))


class _EmptyTrapper(Trapper):
    name = "empty"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# FakeResponse
# ---------------------------------------------------------------------------


def test_fake_response_returns_response():
    r = FakeResponse("https://example.com", "<html></html>")
    assert isinstance(r, Response)


def test_fake_response_url():
    r = FakeResponse("https://example.com/page", "<html></html>")
    assert r.url == "https://example.com/page"


def test_fake_response_status_default():
    r = FakeResponse("https://example.com", "")
    assert r.status == 200


def test_fake_response_custom_status():
    r = FakeResponse("https://example.com", "", status=404)
    assert r.status == 404


def test_fake_response_html_body():
    r = FakeResponse("https://example.com", "<h1>Hello</h1>")
    assert "<h1>Hello</h1>" in r.text


def test_fake_response_encoding():
    r = FakeResponse("https://example.com", "café", encoding="latin-1")
    assert r.encoding == "latin-1"
    assert "café" in r.text


def test_fake_response_custom_headers():
    r = FakeResponse("https://example.com", "", headers={"x-custom": "value"})
    assert r.headers["x-custom"] == "value"


def test_fake_response_has_request():
    r = FakeResponse("https://example.com", "")
    assert r.request is not None
    assert r.request.url == "https://example.com"


def test_fake_response_meta_in_request():
    r = FakeResponse("https://example.com", "", meta={"depth": 3})
    assert r.request is not None
    assert r.request.meta["depth"] == 3


def test_fake_response_selector_works():
    r = FakeResponse("https://example.com", "<h1>Hi there</h1>")
    assert r.selector.css("h1::text").get() == "Hi there"


# ---------------------------------------------------------------------------
# collect_parse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_parse_items():
    r = FakeResponse("https://example.com", "<h1>Test</h1>")
    requests, items = await collect_parse(_TitleTrapper(), r)
    assert len(items) == 1
    assert isinstance(items[0], _TitleItem)
    assert items[0].url == "https://example.com"


@pytest.mark.asyncio
async def test_collect_parse_requests():
    r = FakeResponse("https://example.com", '<a href="/page">link</a>')
    requests, items = await collect_parse(_LinkTrapper(), r)
    assert len(requests) == 1
    assert requests[0].url == "https://example.com/page"
    assert items == []


@pytest.mark.asyncio
async def test_collect_parse_empty():
    r = FakeResponse("https://example.com", "")
    requests, items = await collect_parse(_EmptyTrapper(), r)
    assert requests == []
    assert items == []


@pytest.mark.asyncio
async def test_collect_parse_separates_types():
    class _Mixed(Trapper):
        name = "mixed"
        start_urls: list[str] = []

        async def parse(self, response: Response):  # type: ignore[override]
            yield Request(url="https://next.com")
            yield _TitleItem(url=response.url, title="hello")

    r = FakeResponse("https://example.com", "")
    requests, items = await collect_parse(_Mixed(), r)
    assert len(requests) == 1
    assert len(items) == 1


# ---------------------------------------------------------------------------
# assert_items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assert_items_passes_on_match():
    r = FakeResponse("https://example.com", "<h1>Hello</h1>")
    await assert_items(
        _TitleTrapper(),
        r,
        [{"url": "https://example.com", "title": "Hello"}],
    )


@pytest.mark.asyncio
async def test_assert_items_partial_fields():
    r = FakeResponse("https://example.com", "<h1>World</h1>")
    await assert_items(_TitleTrapper(), r, [{"title": "World"}])


@pytest.mark.asyncio
async def test_assert_items_fails_on_count_mismatch():
    r = FakeResponse("https://example.com", "<h1>Hello</h1>")
    with pytest.raises(AssertionError, match="Expected 0"):
        await assert_items(_TitleTrapper(), r, [])


@pytest.mark.asyncio
async def test_assert_items_fails_on_value_mismatch():
    r = FakeResponse("https://example.com", "<h1>Hello</h1>")
    with pytest.raises(AssertionError, match="title"):
        await assert_items(_TitleTrapper(), r, [{"title": "Wrong title"}])


@pytest.mark.asyncio
async def test_assert_items_empty_expected_on_empty_parse():
    r = FakeResponse("https://example.com", "")
    await assert_items(_EmptyTrapper(), r, [])
