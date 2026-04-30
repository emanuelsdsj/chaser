from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import pytest

from chaser.browser.client import BrowserClient
from chaser.net.request import Request
from chaser.net.response import Response

# ---------------------------------------------------------------------------
# Import guard — playwright not installed
# ---------------------------------------------------------------------------


def test_import_guard_raises_on_enter() -> None:
    """BrowserClient.__aenter__ must give a helpful ImportError when playwright
    is not installed, rather than a confusing AttributeError."""

    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):

        async def _check() -> None:
            client = BrowserClient()
            with pytest.raises(ImportError, match="playwright is required"):
                await client.__aenter__()

        import asyncio

        asyncio.get_event_loop().run_until_complete(_check())


# ---------------------------------------------------------------------------
# fetch() without context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_without_context_manager_raises() -> None:
    client = BrowserClient()
    with pytest.raises(RuntimeError, match="not running"):
        await client.fetch(Request(url="https://example.com"))


# ---------------------------------------------------------------------------
# Constructor defaults
# ---------------------------------------------------------------------------


def test_defaults() -> None:
    client = BrowserClient()
    assert client._headless is True
    assert client._timeout == 30.0
    assert client._wait_until == "load"


def test_custom_params() -> None:
    client = BrowserClient(headless=False, timeout=60.0, wait_until="networkidle")
    assert client._headless is False
    assert client._timeout == 60.0
    assert client._wait_until == "networkidle"


# ---------------------------------------------------------------------------
# fetch() — mocked playwright
# ---------------------------------------------------------------------------


def _make_playwright_mock(html: str = "<html><body>hi</body></html>", status: int = 200):
    """Build a minimal mock of the playwright async API."""
    pw_response = AsyncMock()
    pw_response.status = status
    pw_response.all_headers = AsyncMock(return_value={"content-type": "text/html"})

    page = AsyncMock()
    page.url = "https://example.com/"
    page.goto = AsyncMock(return_value=pw_response)
    page.content = AsyncMock(return_value=html)
    page.set_extra_http_headers = AsyncMock()
    page.close = AsyncMock()

    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page)
    browser.close = AsyncMock()

    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)

    playwright_obj = AsyncMock()
    playwright_obj.chromium = chromium
    playwright_obj.stop = AsyncMock()

    async_playwright_cm = AsyncMock()
    async_playwright_cm.start = AsyncMock(return_value=playwright_obj)

    return async_playwright_cm, browser, page


@pytest.mark.asyncio
async def test_fetch_returns_response() -> None:
    _, browser, _ = _make_playwright_mock()

    client = BrowserClient()
    client._browser = browser
    client._playwright = MagicMock()
    client._playwright.stop = AsyncMock()

    response = await client.fetch(Request(url="https://example.com/"))

    assert isinstance(response, Response)
    assert response.status == 200
    assert response.url == "https://example.com/"
    assert b"hi" in response.body


@pytest.mark.asyncio
async def test_fetch_sets_extra_headers() -> None:
    _, browser, page = _make_playwright_mock()

    client = BrowserClient()
    client._browser = browser
    client._playwright = MagicMock()

    from chaser.net.headers import Headers

    req = Request(url="https://example.com/", headers=Headers({"X-Token": "abc"}))
    await client.fetch(req)

    page.set_extra_http_headers.assert_called_once()
    call_args = page.set_extra_http_headers.call_args[0][0]
    assert call_args.get("x-token") == "abc"


@pytest.mark.asyncio
async def test_fetch_page_always_closed() -> None:
    """Page must be closed even if an exception occurs mid-fetch."""
    _, browser, page = _make_playwright_mock()
    page.goto = AsyncMock(side_effect=RuntimeError("navigation failed"))

    client = BrowserClient()
    client._browser = browser
    client._playwright = MagicMock()

    with pytest.raises(RuntimeError, match="navigation failed"):
        await client.fetch(Request(url="https://example.com/"))

    page.close.assert_called_once()


@pytest.mark.asyncio
async def test_aexit_clears_state() -> None:
    _, browser, _ = _make_playwright_mock()

    playwright_mock = MagicMock()
    playwright_mock.stop = AsyncMock()

    client = BrowserClient()
    client._browser = browser
    client._playwright = playwright_mock

    await client.__aexit__(None, None, None)

    browser.close.assert_called_once()
    playwright_mock.stop.assert_called_once()
    assert client._browser is None
    assert client._playwright is None
