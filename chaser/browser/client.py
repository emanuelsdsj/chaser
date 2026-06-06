from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from chaser.net.headers import Headers
from chaser.net.response import Response

if TYPE_CHECKING:
    from chaser.browser.stealth import StealthConfig
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

    Pass ``stealth=StealthConfig()`` to randomize UA, viewport, timezone and
    locale per request and suppress the ``navigator.webdriver`` flag.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: float = 30.0,
        wait_until: str = "load",
        stealth: StealthConfig | None = None,
    ) -> None:
        self._headless = headless
        self._timeout = timeout
        self._wait_until = wait_until
        self._stealth = stealth
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

        When stealth is disabled each call opens a bare page and closes it.
        When stealth is enabled a fresh browser context is created per request
        with randomized UA, viewport, timezone and locale.
        """
        if self._browser is None:
            raise RuntimeError("BrowserClient is not running — use it as an async context manager")

        if self._stealth is not None:
            return await self._fetch_with_stealth(request)
        return await self._fetch_plain(request)

    async def _fetch_plain(self, request: Request) -> Response:
        page = await self._browser.new_page()
        try:
            return await self._navigate(page, request)
        finally:
            await page.close()

    async def _fetch_with_stealth(self, request: Request) -> Response:
        from chaser.browser.stealth import STEALTH_INIT_SCRIPT

        assert self._stealth is not None
        ctx = await self._browser.new_context(**self._stealth.random_context_options())
        try:
            page = await ctx.new_page()
            await page.add_init_script(STEALTH_INIT_SCRIPT)
            return await self._navigate(page, request)
        finally:
            await ctx.close()

    async def _navigate(self, page: Any, request: Request) -> Response:
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
