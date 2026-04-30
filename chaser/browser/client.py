from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from chaser.net.headers import Headers
from chaser.net.response import Response

if TYPE_CHECKING:
    from chaser.net.request import Request


class BrowserClient:
    """Playwright-backed async fetch client for JavaScript-heavy pages.

    Returns the same ``Response`` type as ``NetClient`` so it can be used
    interchangeably wherever the response interface is expected.

    ``playwright`` is an optional dependency — install it with::

        pip install "chaser[browser]"
        playwright install chromium

    Usage::

        async with BrowserClient() as browser:
            response = await browser.fetch(Request(url="https://example.com"))
            title = response.selector.css("title::text").get()

    Pass ``headless=False`` for debugging; ``wait_until`` controls when
    Playwright considers the page loaded (``"load"``, ``"networkidle"``,
    ``"domcontentloaded"``).
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: float = 30.0,
        wait_until: str = "load",
    ) -> None:
        self._headless = headless
        self._timeout = timeout
        self._wait_until = wait_until
        self._playwright: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> BrowserClient:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ImportError(
                "playwright is required for BrowserClient.\n"
                "Install it with: pip install 'chaser[browser]' && playwright install chromium"
            ) from exc

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def fetch(self, request: Request) -> Response:
        """Fetch *request* in a browser page and return a ``Response``.

        Each call opens a fresh page and closes it after the response is
        captured — no shared page state between requests.
        """
        if self._browser is None:
            raise RuntimeError("BrowserClient is not running — use it as an async context manager")

        page = await self._browser.new_page()
        try:
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

            return Response(
                url=page.url,
                status=status,
                headers=Headers(raw_headers),
                body=html.encode("utf-8"),
                encoding="utf-8",
                elapsed=elapsed,
                request=request,
            )
        finally:
            await page.close()
