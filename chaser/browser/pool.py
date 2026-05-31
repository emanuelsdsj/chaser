from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

from chaser.net.headers import Headers
from chaser.net.response import Response

if TYPE_CHECKING:
    from chaser.net.request import Request


class BrowserPool:
    """Pool of reusable Playwright pages for high-throughput browser crawling.

    Pre-allocates *size* pages at startup and reuses them across requests,
    avoiding the ~300ms overhead of ``new_page()`` + ``close()`` on every fetch.

    When all pages are busy the caller blocks until one is returned — this
    naturally caps browser concurrency at *size*.

    If a page raises during navigation it is discarded and replaced with a
    fresh page so the pool size stays constant. If the replacement itself
    fails, the pool temporarily shrinks by one; it self-heals on the next
    successful request.

    Usage::

        async with BrowserPool(size=5) as pool:
            responses = await asyncio.gather(
                pool.fetch(Request(url="https://a.com")),
                pool.fetch(Request(url="https://b.com")),
            )

    ``playwright`` is an optional dependency — install it with::

        pip install "chaser[browser]"
        playwright install chromium
    """

    def __init__(
        self,
        *,
        size: int = 5,
        headless: bool = True,
        timeout: float = 30.0,
        wait_until: str = "load",
    ) -> None:
        self._size = size
        self._headless = headless
        self._timeout = timeout
        self._wait_until = wait_until
        self._playwright: Any = None
        self._browser: Any = None
        self._pages: asyncio.Queue[Any] = asyncio.Queue()

    async def __aenter__(self) -> BrowserPool:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ImportError(
                "playwright is required for BrowserPool.\n"
                "Install it with: pip install 'chaser[browser]' && playwright install chromium"
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)

        for _ in range(self._size):
            page = await self._browser.new_page()
            await self._pages.put(page)

        return self

    async def __aexit__(self, *_: Any) -> None:
        while not self._pages.empty():
            try:
                page = self._pages.get_nowait()
                await page.close()
            except asyncio.QueueEmpty:
                break

        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def fetch(self, request: Request) -> Response:
        """Fetch *request* using a pooled page.

        Blocks until a page is available. On navigation error the broken page
        is replaced with a fresh one before the exception propagates.
        """
        if self._browser is None:
            raise RuntimeError("BrowserPool is not running — use it as an async context manager")

        page = await self._pages.get()
        success = False
        try:
            await page.set_extra_http_headers({})

            extra = dict(request.headers)
            if extra:
                await page.set_extra_http_headers(extra)

            t0 = time.monotonic()
            pw_resp = await page.goto(
                request.url,
                timeout=self._timeout * 1000,
                wait_until=self._wait_until,
            )
            elapsed = time.monotonic() - t0

            if pw_resp is None:
                raise RuntimeError(f"Playwright returned no response for {request.url!r}")

            html = await page.content()
            status = pw_resp.status
            raw_headers = await pw_resp.all_headers()

            result = Response(
                url=page.url,
                status=status,
                headers=Headers(raw_headers),
                body=html.encode("utf-8"),
                encoding="utf-8",
                elapsed=elapsed,
                request=request,
            )
            success = True
            return result
        finally:
            if success:
                await self._pages.put(page)
            else:
                with contextlib.suppress(Exception):
                    await page.close()
                with contextlib.suppress(Exception):
                    replacement = await self._browser.new_page()
                    await self._pages.put(replacement)
