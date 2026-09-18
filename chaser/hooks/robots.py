from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from chaser.hooks.base import FetchHook, RequestAborted
from chaser.net.request import Request

logger = logging.getLogger(__name__)

# The stdlib's default User-Agent for this fetch (`Python-urllib/x.y`) gets
# flagged and 403'd by some sites' WAFs even when their robots.txt explicitly
# allows `*` — which RobotFileParser.read() then misreads as "disallow
# everything" (401/403 -> disallow_all=True), blocking a crawl the site never
# meant to block. A generic browser UA avoids that false negative.
DEFAULT_ROBOTS_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


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

    def __init__(
        self,
        user_agent: str = "*",
        fetch_user_agent: str = DEFAULT_ROBOTS_FETCH_USER_AGENT,
    ) -> None:
        self._user_agent = user_agent
        self._fetch_user_agent = fetch_user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _domain_lock(self, base_url: str) -> asyncio.Lock:
        if base_url not in self._locks:
            self._locks[base_url] = asyncio.Lock()
        return self._locks[base_url]

    def _fetch_robots_txt(self, parser: RobotFileParser) -> None:
        """Fetches robots.txt with a real User-Agent header.

        Diverges from stdlib's RobotFileParser.read() on HTTP error
        responses: read() treats a 401/403 on robots.txt itself as "disallow
        everything", which silently blocks a crawl the site never meant to
        block whenever a WAF flags the *fetch* (e.g. by User-Agent) rather
        than the site actually restricting access. This mirrors the class's
        own documented contract — a robots.txt fetch that fails for any
        reason allows the request — by treating every HTTP error response
        the same way: no rules could be read, so no rules are enforced. A
        genuine network failure (no response at all) isn't caught here; it
        propagates so ``before_request`` applies that same "allow" fallback.
        """
        request = urllib.request.Request(
            parser.url,  # type: ignore[attr-defined]
            headers={"User-Agent": self._fetch_user_agent},
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read()
        except urllib.error.HTTPError:
            parser.allow_all = True  # type: ignore[attr-defined]
            return
        parser.parse(raw.decode("utf-8", errors="replace").splitlines())

    async def _parser_for(self, base_url: str) -> RobotFileParser:
        lock = self._domain_lock(base_url)
        async with lock:
            if base_url in self._parsers:
                return self._parsers[base_url]
            parser = RobotFileParser(url=f"{base_url}/robots.txt")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._fetch_robots_txt, parser)
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
