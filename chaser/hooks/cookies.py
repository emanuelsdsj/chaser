from __future__ import annotations

import asyncio
from http.cookies import SimpleCookie
from urllib.parse import urlparse

from chaser.hooks.base import FetchHook
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


class CookieJarHook(FetchHook):
    """Per-domain session cookie jar.

    Reads Set-Cookie from responses and re-injects cookies into subsequent
    requests to the same domain. Works across redirect chains because the
    URL on the response is the final URL after redirects.

    Multiple Set-Cookie headers from the same response are joined with newlines
    in NetClient and split back here, so all cookies are captured correctly.
    """

    def __init__(self) -> None:
        self._jar: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def before_request(self, request: Request) -> Request:
        domain = self._domain(request.url)
        async with self._lock:
            cookies = dict(self._jar.get(domain, {}))
        if not cookies:
            return request
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        merged = dict(request.headers)
        merged["cookie"] = cookie_str
        return request.copy(headers=Headers(merged))

    async def after_response(self, response: Response) -> Response:
        raw_header = response.headers.get("set-cookie")
        if not raw_header:
            return response
        domain = self._domain(response.url)
        async with self._lock:
            bucket = self._jar.setdefault(domain, {})
            for line in raw_header.split("\n"):
                if line.strip():
                    parsed: SimpleCookie = SimpleCookie()
                    parsed.load(line)
                    for key, morsel in parsed.items():
                        bucket[key] = morsel.value
        return response
