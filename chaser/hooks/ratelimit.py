from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from chaser.hooks.base import FetchHook
from chaser.net.request import Request


class _Bucket:
    def __init__(self, rate: float, burst: int) -> None:
        self._rate = rate
        self._burst = float(burst)
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait)


class RateLimitHook(FetchHook):
    """Per-domain token bucket. Throttles requests to each domain independently.

    Args:
        rate: sustained requests per second per domain (default 1.0)
        burst: max simultaneous tokens — controls burst headroom (default 1)
    """

    def __init__(self, rate: float = 1.0, burst: int = 1) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: dict[str, _Bucket] = {}

    def _bucket(self, domain: str) -> _Bucket:
        if domain not in self._buckets:
            self._buckets[domain] = _Bucket(self._rate, self._burst)
        return self._buckets[domain]

    async def before_request(self, request: Request) -> Request:
        domain = urlparse(request.url).netloc
        await self._bucket(domain).acquire()
        return request
