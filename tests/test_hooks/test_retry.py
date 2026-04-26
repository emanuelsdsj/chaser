from __future__ import annotations

from unittest.mock import patch

from chaser.hooks.retry import RetryPolicy
from chaser.net.client import CircuitOpenError, FetchError


class TestRetryPolicy:
    def test_retries_on_fetch_error(self) -> None:
        policy = RetryPolicy(max_retries=3)
        err = FetchError("connection refused")
        assert policy.should_retry(0, err)
        assert policy.should_retry(2, err)

    def test_stops_after_max_retries(self) -> None:
        policy = RetryPolicy(max_retries=3)
        assert not policy.should_retry(3, FetchError("timeout"))

    def test_does_not_retry_non_fetch_errors(self) -> None:
        policy = RetryPolicy(max_retries=5)
        assert not policy.should_retry(0, ValueError("unexpected"))
        assert not policy.should_retry(0, CircuitOpenError("open"))

    async def test_wait_grows_exponentially(self) -> None:
        policy = RetryPolicy(base_delay=1.0, max_delay=100.0, jitter=False)
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        with patch("chaser.hooks.retry.asyncio.sleep", fake_sleep):
            await policy.wait(0)  # 1.0s
            await policy.wait(1)  # 2.0s
            await policy.wait(2)  # 4.0s

        assert slept == [1.0, 2.0, 4.0]

    async def test_wait_is_capped_at_max_delay(self) -> None:
        policy = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter=False)
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        with patch("chaser.hooks.retry.asyncio.sleep", fake_sleep):
            await policy.wait(10)  # 1024s uncapped, 5.0s after cap

        assert slept == [5.0]

    async def test_jitter_varies_the_delay(self) -> None:
        policy = RetryPolicy(base_delay=1.0, max_delay=10.0, jitter=True)
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        with patch("chaser.hooks.retry.asyncio.sleep", fake_sleep):
            for _ in range(8):
                await policy.wait(0)

        # With uniform(0.5, 1.5) jitter the values should vary
        assert max(slept) != min(slept)
        # Bounds: base * max_jitter = 1.0 * 1.5 = 1.5
        assert all(0.4 <= d <= 1.6 for d in slept)
