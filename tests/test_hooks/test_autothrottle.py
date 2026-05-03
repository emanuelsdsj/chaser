from __future__ import annotations

from unittest.mock import AsyncMock, patch

from chaser.hooks.autothrottle import AutoThrottleHook
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


def _response(url: str, elapsed: float) -> Response:
    return Response(url=url, status=200, headers=Headers(), body=b"", elapsed=elapsed)


class TestAutoThrottleHook:
    async def test_no_delay_on_first_request(self) -> None:
        hook = AutoThrottleHook()
        req = Request("http://example.com/")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await hook.before_request(req)
            mock_sleep.assert_not_called()

    async def test_delay_set_after_first_response(self) -> None:
        hook = AutoThrottleHook()
        await hook.after_response(_response("http://example.com/", elapsed=0.5))
        assert hook._delays["example.com"] == 0.5

    async def test_delay_applied_on_next_request(self) -> None:
        hook = AutoThrottleHook()
        await hook.after_response(_response("http://example.com/", elapsed=0.3))
        req = Request("http://example.com/page")
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await hook.before_request(req)
            mock_sleep.assert_called_once()
            assert abs(mock_sleep.call_args[0][0] - 0.3) < 0.01

    async def test_rolling_average_smooths_spikes(self) -> None:
        hook = AutoThrottleHook(window=4)
        for elapsed in [0.1, 0.1, 0.1, 1.0]:
            await hook.after_response(_response("http://example.com/", elapsed=elapsed))
        # average of [0.1, 0.1, 0.1, 1.0] = 0.325, not the spike value 1.0
        assert hook._delays["example.com"] < 0.5

    async def test_delay_clamped_to_max(self) -> None:
        hook = AutoThrottleHook(max_delay=2.0)
        await hook.after_response(_response("http://example.com/", elapsed=99.0))
        assert hook._delays["example.com"] == 2.0

    async def test_delay_clamped_to_min(self) -> None:
        hook = AutoThrottleHook(min_delay=0.5)
        await hook.after_response(_response("http://example.com/", elapsed=0.01))
        assert hook._delays["example.com"] == 0.5

    async def test_domains_are_isolated(self) -> None:
        hook = AutoThrottleHook()
        await hook.after_response(_response("http://site-a.com/", elapsed=1.0))
        await hook.after_response(_response("http://site-b.com/", elapsed=0.1))
        assert hook._delays["site-a.com"] != hook._delays["site-b.com"]
