from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chaser.hooks.bandwidth import BandwidthThrottleHook, _ByteBucket
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


def _response(body: bytes, url: str = "http://example.com/") -> Response:
    req = Request(url)
    return Response(url=url, status=200, headers=Headers(), body=body, request=req)


def _response_no_req(body: bytes, url: str = "http://example.com/") -> Response:
    return Response(url=url, status=200, headers=Headers(), body=body)


class TestByteBucket:
    async def test_empty_acquire_returns_immediately(self) -> None:
        bucket = _ByteBucket(rate_bps=100, burst_bytes=100)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bucket.acquire(0)
            mock_sleep.assert_not_called()

    async def test_within_burst_no_sleep(self) -> None:
        bucket = _ByteBucket(rate_bps=100, burst_bytes=100)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bucket.acquire(100)
            mock_sleep.assert_not_called()

    async def test_over_burst_sleeps_proportionally(self) -> None:
        # burst=100 bytes, rate=100 B/s; requesting 200 bytes → deficit=100 → wait=1.0s
        bucket = _ByteBucket(rate_bps=100, burst_bytes=100)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bucket.acquire(200)
            mock_sleep.assert_called_once()
            assert abs(mock_sleep.call_args[0][0] - 1.0) < 0.01

    async def test_larger_than_burst_handled(self) -> None:
        # burst=10 bytes, rate=10 B/s; requesting 50 bytes → deficit=40 → wait=4.0s
        bucket = _ByteBucket(rate_bps=10, burst_bytes=10)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bucket.acquire(50)
            mock_sleep.assert_called_once()
            assert abs(mock_sleep.call_args[0][0] - 4.0) < 0.01

    async def test_second_acquire_drains_correctly(self) -> None:
        bucket = _ByteBucket(rate_bps=100, burst_bytes=100)
        # First call exhausts burst — no sleep
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bucket.acquire(100)
        # Second call immediately after — full deficit of 50 bytes at 100 B/s → 0.5s
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bucket.acquire(50)
            mock_sleep.assert_called_once()
            assert abs(mock_sleep.call_args[0][0] - 0.5) < 0.05


class TestBandwidthThrottleHook:
    async def test_empty_body_no_sleep(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0)
        resp = _response(b"")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await hook.after_response(resp)
            mock_sleep.assert_not_called()
        assert result is resp

    async def test_response_within_burst_no_sleep(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0, burst_mb=1.0)
        body = b"x" * (512 * 1024)  # 512 KB — half the 1 MB burst
        resp = _response(body)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await hook.after_response(resp)
            mock_sleep.assert_not_called()

    async def test_response_over_burst_sleeps(self) -> None:
        # rate=1 MB/s, burst=0.5 MB → 1 MB body causes ~0.5s sleep
        hook = BandwidthThrottleHook(rate_mbps=1.0, burst_mb=0.5)
        body = b"x" * (1024 * 1024)  # 1 MB
        resp = _response(body)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await hook.after_response(resp)
            mock_sleep.assert_called_once()
            wait = mock_sleep.call_args[0][0]
            assert 0.4 < wait < 0.6

    async def test_per_domain_buckets_are_independent(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0, burst_mb=0.1)
        body = b"x" * (200 * 1024)  # 200 KB — over the 100 KB burst

        resp_a = _response(body, url="http://a.com/page")
        resp_b = _response(body, url="http://b.com/page")

        sleep_calls: list[float] = []

        async def record_sleep(t: float) -> None:
            sleep_calls.append(t)

        with patch("asyncio.sleep", side_effect=record_sleep):
            await hook.after_response(resp_a)  # a.com throttled
            await hook.after_response(resp_b)  # b.com has fresh bucket — also throttled
            # both domains throttled independently (2 separate sleeps)
            assert len(sleep_calls) == 2

    async def test_global_mode_shared_bucket(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0, burst_mb=0.1, per_domain=False)
        body = b"x" * (200 * 1024)  # over burst

        resp_a = _response(body, url="http://a.com/page")

        sleep_calls: list[float] = []

        async def record_sleep(t: float) -> None:
            sleep_calls.append(t)

        with patch("asyncio.sleep", side_effect=record_sleep):
            await hook.after_response(resp_a)

        # second domain — global bucket is now empty, sleep for full body
        resp_b = _response(body, url="http://b.com/page")
        sleep_calls.clear()
        with patch("asyncio.sleep", side_effect=record_sleep):
            await hook.after_response(resp_b)
        # both go through the same bucket, so both get throttled
        assert len(sleep_calls) >= 1

    async def test_fallback_to_response_url_when_no_request(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0, burst_mb=1.0)
        resp = _response_no_req(b"x" * 100)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await hook.after_response(resp)
            assert result is resp
            mock_sleep.assert_not_called()

    async def test_default_burst_is_two_seconds_of_rate(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=1.0)
        # default burst = 2 * 1.0 MB = 2 MB
        assert hook._burst_bytes == pytest.approx(2 * 1024 * 1024)

    async def test_response_object_returned_unchanged(self) -> None:
        hook = BandwidthThrottleHook(rate_mbps=100.0, burst_mb=100.0)
        resp = _response(b"hello")
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await hook.after_response(resp)
        assert result is resp
        assert result.body == b"hello"
