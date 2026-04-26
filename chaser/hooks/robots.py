from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from chaser.hooks.base import FetchHook, RequestAborted
from chaser.net.request import Request

logger = logging.getLogger(__name__)


class RobotsDisallowedError(RequestAborted):
    """The URL is explicitly disallowed by the site's robots.txt."""


class RobotsHook(FetchHook):
    """Fetches and caches robots.txt per domain, rejects disallowed URLs.

    robots.txt is fetched exactly once per domain (using urllib in a thread
    pool to avoid blocking the event loop) and cached for the hook's lifetime.

    If fetching robots.txt fails for any reason, the request is allowed —
    paranoid blocking would break crawls on sites without a robots.txt.

    Raises ``RobotsDisallowedError`` (subclass of ``RequestAborted``) when a
    URL is blocked. The engine logs at DEBUG and skips the URL cleanly.
    """

    def __init__(self, user_agent: str = "*") -> None:
        self._user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _domain_lock(self, base_url: str) -> asyncio.Lock:
        if base_url not in self._locks:
            self._locks[base_url] = asyncio.Lock()
        return self._locks[base_url]

    async def _parser_for(self, base_url: str) -> RobotFileParser:
        lock = self._domain_lock(base_url)
        async with lock:
            if base_url in self._parsers:
                return self._parsers[base_url]
            parser = RobotFileParser(url=f"{base_url}/robots.txt")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, parser.read)
            self._parsers[base_url] = parser
            return parser

    async def before_request(self, request: Request) -> Request:
        p = urlparse(request.url)
        base = f"{p.scheme}://{p.netloc}"
        try:
            parser = await self._parser_for(base)
        except Exception:
            logger.warning("Could not fetch robots.txt for %s — allowing request", base)
            return request
        if not parser.can_fetch(self._user_agent, request.url):
            raise RobotsDisallowedError(f"robots.txt disallows {request.url!r}")
        return request
