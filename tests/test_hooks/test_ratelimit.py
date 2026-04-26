from __future__ import annotations

import time

from chaser.hooks.ratelimit import RateLimitHook
from chaser.net.request import Request


class TestRateLimitHook:
    async def test_first_request_passes_immediately(self) -> None:
        hook = RateLimitHook(rate=1.0, burst=1)
        req = Request("http://example.com/")
        t0 = time.monotonic()
        result = await hook.before_request(req)
        assert time.monotonic() - t0 < 0.1
        assert result is req

    async def test_throttles_after_burst_exhausted(self) -> None:
        # burst=1 at 10 rps → second request must wait ~0.1s
        hook = RateLimitHook(rate=10.0, burst=1)
        req = Request("http://example.com/")
        await hook.before_request(req)  # consumes the single token
        t0 = time.monotonic()
        await hook.before_request(req)
        assert time.monotonic() - t0 >= 0.08

    async def test_domains_have_independent_buckets(self) -> None:
        hook = RateLimitHook(rate=10.0, burst=1)
        req_a = Request("http://a.com/")
        req_b = Request("http://b.com/")
        await hook.before_request(req_a)  # exhausts a.com's bucket
        # b.com still has a full token — should not block
        t0 = time.monotonic()
        await hook.before_request(req_b)
        assert time.monotonic() - t0 < 0.05

    async def test_request_object_is_not_modified(self) -> None:
        hook = RateLimitHook()
        req = Request("http://example.com/", headers={"x-custom": "value"})
        result = await hook.before_request(req)
        assert result is req
        assert result.headers.get("x-custom") == "value"
