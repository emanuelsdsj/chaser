from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urlparse

from chaser.hooks.base import FetchHook
from chaser.net.request import Request
from chaser.net.response import Response


class AutoThrottleHook(FetchHook):
    """Adaptive rate limiter that matches request pace to server response time.

    Tracks a rolling average of response latency per domain and sleeps for
    that duration before each request. Fast servers get more traffic; slow
    servers get less — automatically, without manual tuning.

    ``min_delay`` and ``max_delay`` bound the computed sleep to avoid
    hammering or stalling. ``window`` controls smoothing: larger values react
    more slowly to latency spikes.

    Don't stack with RateLimitHook — both act in before_request and the
    delays are additive.
    """

    def __init__(
        self,
        min_delay: float = 0.0,
        max_delay: float = 60.0,
        window: int = 8,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._window = window
        self._samples: dict[str, deque[float]] = {}
        self._delays: dict[str, float] = {}

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def before_request(self, request: Request) -> Request:
        domain = self._domain(request.url)
        delay = self._delays.get(domain, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        return request

    async def after_response(self, response: Response) -> Response:
        domain = self._domain(response.url)
        if domain not in self._samples:
            self._samples[domain] = deque(maxlen=self._window)
        self._samples[domain].append(response.elapsed)
        avg = sum(self._samples[domain]) / len(self._samples[domain])
        self._delays[domain] = max(self._min_delay, min(avg, self._max_delay))
        return response
