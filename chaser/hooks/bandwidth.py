from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from chaser.hooks.base import FetchHook
from chaser.net.response import Response

_MB = 1024 * 1024


class _ByteBucket:
    """Token bucket that counts bytes instead of requests."""

    def __init__(self, rate_bps: float, burst_bytes: float) -> None:
        self._rate = rate_bps
        self._burst = burst_bytes
        self._tokens = burst_bytes
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, nbytes: int) -> None:
        if nbytes <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= nbytes:
                self._tokens -= nbytes
                return
            deficit = nbytes - self._tokens
            wait = deficit / self._rate
            self._tokens = 0
            self._last = now + wait
        await asyncio.sleep(wait)


class BandwidthThrottleHook(FetchHook):
    """Limits download throughput by sleeping after large responses.

    Uses a token bucket counted in bytes, not requests. After each response
    the hook checks how many bytes were downloaded and sleeps long enough to
    keep sustained throughput at or below ``rate_mbps``.

    Works alongside RateLimitHook — the two throttle orthogonal dimensions:
    requests/s vs. bytes/s.

    Args:
        rate_mbps: sustained download rate per domain in MB/s (default 1.0)
        burst_mb: burst headroom in MB before throttling kicks in.
            Defaults to two seconds' worth of data at ``rate_mbps``.
        per_domain: when True (default), each domain gets its own bucket;
            when False, a single global bucket covers all domains.
    """

    def __init__(
        self,
        rate_mbps: float = 1.0,
        burst_mb: float | None = None,
        *,
        per_domain: bool = True,
    ) -> None:
        self._rate_bps = rate_mbps * _MB
        self._burst_bytes = (burst_mb if burst_mb is not None else rate_mbps * 2) * _MB
        self._per_domain = per_domain
        self._buckets: dict[str, _ByteBucket] = {}
        self._global: _ByteBucket | None = None if per_domain else self._make_bucket()

    def _make_bucket(self) -> _ByteBucket:
        return _ByteBucket(self._rate_bps, self._burst_bytes)

    def _bucket(self, domain: str) -> _ByteBucket:
        if self._global is not None:
            return self._global
        if domain not in self._buckets:
            self._buckets[domain] = self._make_bucket()
        return self._buckets[domain]

    async def after_response(self, response: Response) -> Response:
        url = response.request.url if response.request is not None else response.url
        domain = urlparse(url).netloc
        await self._bucket(domain).acquire(len(response.body))
        return response
