from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from chaser.browser.pool import BrowserPool
from chaser.net.request import Request
from chaser.net.response import Response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_page(html: str = "<html><body>pool</body></html>", status: int = 200) -> AsyncMock:
    pw_response = AsyncMock()
    pw_response.status = status
    pw_response.all_headers = AsyncMock(return_value={"content-type": "text/html"})

    page = AsyncMock()
    page.url = "https://example.com/"
    page.goto = AsyncMock(return_value=pw_response)
    page.content = AsyncMock(return_value=html)
    page.set_extra_http_headers = AsyncMock()
    page.close = AsyncMock()
    return page


def _make_browser(pages: list[AsyncMock]) -> AsyncMock:
    """Return a browser mock whose new_page() yields pages in sequence."""
    browser = AsyncMock()
    browser.new_page = AsyncMock(side_effect=pages)
    browser.close = AsyncMock()
    return browser


def _make_playwright(browser: AsyncMock) -> tuple[AsyncMock, AsyncMock]:
    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    playwright_obj = AsyncMock()
    playwright_obj.chromium = chromium
    playwright_obj.stop = AsyncMock()

    cm = AsyncMock()
    cm.start = AsyncMock(return_value=playwright_obj)
    return cm, playwright_obj


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_defaults() -> None:
    pool = BrowserPool()
    assert pool._size == 5
    assert pool._headless is True
    assert pool._timeout == 30.0
    assert pool._wait_until == "load"


def test_custom_params() -> None:
    pool = BrowserPool(size=3, headless=False, timeout=60.0, wait_until="networkidle")
    assert pool._size == 3
    assert pool._headless is False
    assert pool._timeout == 60.0
    assert pool._wait_until == "networkidle"


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


def test_import_guard_raises_on_enter() -> None:
    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):

        async def _check() -> None:
            pool = BrowserPool()
            with pytest.raises(ImportError, match="playwright is required"):
                await pool.__aenter__()

        asyncio.get_event_loop().run_until_complete(_check())


# ---------------------------------------------------------------------------
# fetch() without context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_without_context_manager_raises() -> None:
    pool = BrowserPool()
    with pytest.raises(RuntimeError, match="not running"):
        await pool.fetch(Request(url="https://example.com"))


# ---------------------------------------------------------------------------
# __aenter__ pre-allocates pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aenter_preallocates_pages() -> None:
    pages = [_make_page() for _ in range(3)]
    browser = _make_browser(pages)
    cm, _ = _make_playwright(browser)

    pool = BrowserPool(size=3)
    with patch("chaser.browser.pool.async_playwright", return_value=cm, create=True):
        pool._playwright = await cm.start()
        pool._browser = browser
        for page in pages:
            await pool._pages.put(page)

    assert pool._pages.qsize() == 3
    assert browser.new_page.call_count == 0  # we put manually above


@pytest.mark.asyncio
async def test_aenter_calls_new_page_size_times() -> None:
    pages = [_make_page() for _ in range(4)]
    browser = _make_browser(pages[:])
    cm, _ = _make_playwright(browser)

    pool = BrowserPool(size=4)
    pool._playwright = await cm.start()
    pool._browser = browser

    for _ in range(4):
        page = await browser.new_page()
        await pool._pages.put(page)

    assert pool._pages.qsize() == 4
    assert browser.new_page.call_count == 4


# ---------------------------------------------------------------------------
# fetch() — successful request, page returned to pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_returns_response() -> None:
    page = _make_page()
    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    response = await pool.fetch(Request(url="https://example.com/"))

    assert isinstance(response, Response)
    assert response.status == 200
    assert b"pool" in response.body


@pytest.mark.asyncio
async def test_page_returned_to_pool_after_success() -> None:
    page = _make_page()
    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    assert pool._pages.qsize() == 1
    await pool.fetch(Request(url="https://example.com/"))

    # Page must be back in the queue — pool size unchanged
    assert pool._pages.qsize() == 1
    page.close.assert_not_called()


@pytest.mark.asyncio
async def test_same_page_reused_across_requests() -> None:
    page = _make_page()
    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    await pool.fetch(Request(url="https://example.com/"))
    await pool.fetch(Request(url="https://example.com/page2"))

    # new_page should never have been called — same page reused
    browser.new_page.assert_not_called()
    assert page.goto.call_count == 2


# ---------------------------------------------------------------------------
# fetch() — headers reset between requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headers_cleared_before_each_request() -> None:
    page = _make_page()
    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    from chaser.net.headers import Headers

    req = Request(url="https://example.com/", headers=Headers({"X-Token": "abc"}))
    await pool.fetch(req)

    # First call clears headers, second sets the request-specific ones
    calls = page.set_extra_http_headers.call_args_list
    assert calls[0] == call({})
    assert calls[1].args[0].get("x-token") == "abc"


@pytest.mark.asyncio
async def test_no_extra_headers_call_when_request_has_none() -> None:
    page = _make_page()
    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    await pool.fetch(Request(url="https://example.com/"))

    # Only the clear call should happen; no second set call
    page.set_extra_http_headers.assert_called_once_with({})


# ---------------------------------------------------------------------------
# fetch() — page replaced on error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broken_page_replaced_on_error() -> None:
    bad_page = _make_page()
    bad_page.goto = AsyncMock(side_effect=RuntimeError("nav failed"))

    replacement = _make_page()
    browser = _make_browser([replacement])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(bad_page)

    with pytest.raises(RuntimeError, match="nav failed"):
        await pool.fetch(Request(url="https://example.com/"))

    # Bad page must be closed
    bad_page.close.assert_called_once()
    # Replacement was created and put back
    assert pool._pages.qsize() == 1
    browser.new_page.assert_called_once()


@pytest.mark.asyncio
async def test_pool_usable_after_error() -> None:
    bad_page = _make_page()
    bad_page.goto = AsyncMock(side_effect=RuntimeError("boom"))

    good_page = _make_page()
    browser = _make_browser([good_page])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(bad_page)

    with pytest.raises(RuntimeError):
        await pool.fetch(Request(url="https://example.com/"))

    # Pool now has the replacement — next request should succeed
    response = await pool.fetch(Request(url="https://example.com/ok"))
    assert response.status == 200


# ---------------------------------------------------------------------------
# Concurrency — pool size limits simultaneous fetches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_blocks_when_all_pages_busy() -> None:
    """A pool with size=1 must serialize two concurrent requests."""
    goto_calls: list[str] = []

    page = _make_page()

    async def slow_goto(*_args: object, **_kwargs: object) -> AsyncMock:
        goto_calls.append("called")
        await asyncio.sleep(0.05)
        pw_resp = AsyncMock()
        pw_resp.status = 200
        pw_resp.all_headers = AsyncMock(return_value={})
        return pw_resp

    page.goto = slow_goto

    browser = _make_browser([])
    pool = BrowserPool(size=1)
    pool._browser = browser
    pool._playwright = MagicMock()
    await pool._pages.put(page)

    results = await asyncio.gather(
        pool.fetch(Request(url="https://a.com")),
        pool.fetch(Request(url="https://b.com")),
    )

    assert len(results) == 2
    # Both completed — page was reused sequentially
    assert len(goto_calls) == 2


# ---------------------------------------------------------------------------
# __aexit__ — all pages closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aexit_closes_all_pages() -> None:
    pages = [_make_page() for _ in range(3)]
    browser = _make_browser([])
    pool = BrowserPool(size=3)
    pool._browser = browser
    playwright_mock = MagicMock()
    playwright_mock.stop = AsyncMock()
    pool._playwright = playwright_mock

    for page in pages:
        await pool._pages.put(page)

    await pool.__aexit__(None, None, None)

    for page in pages:
        page.close.assert_called_once()

    browser.close.assert_called_once()
    playwright_mock.stop.assert_called_once()
    assert pool._browser is None
    assert pool._playwright is None


@pytest.mark.asyncio
async def test_aexit_clears_internal_state() -> None:
    pool = BrowserPool(size=1)
    browser = _make_browser([])
    playwright_mock = MagicMock()
    playwright_mock.stop = AsyncMock()
    pool._browser = browser
    pool._playwright = playwright_mock

    page = _make_page()
    await pool._pages.put(page)

    await pool.__aexit__(None, None, None)

    assert pool._browser is None
    assert pool._playwright is None
