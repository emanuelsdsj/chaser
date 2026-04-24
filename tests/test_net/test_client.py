from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from chaser.net.client import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    FetchError,
    NetClient,
)
from chaser.net.request import Request

# ---------------------------------------------------------------------------
# CircuitBreaker unit tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker()
        assert cb.state is CircuitState.CLOSED
        assert cb.is_open() is False

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.CLOSED
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        assert cb.is_open() is True

    def test_does_not_open_before_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state is CircuitState.CLOSED

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        # only 2 failures since last success — should still be closed
        assert cb.state is CircuitState.CLOSED

    def test_transitions_to_half_open_after_recovery(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        for _ in range(3):
            cb.record_failure()
        opened_at = cb._opened_at
        assert opened_at is not None

        with patch("chaser.net.client.time.monotonic", return_value=opened_at + 31.0):
            assert cb.state is CircuitState.HALF_OPEN
            assert cb.is_open() is False

    def test_closes_from_half_open_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        for _ in range(3):
            cb.record_failure()
        opened_at = cb._opened_at
        assert opened_at is not None

        with patch("chaser.net.client.time.monotonic", return_value=opened_at + 31.0):
            assert cb.state is CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state is CircuitState.CLOSED

    def test_reopens_from_half_open_on_failure(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
        for _ in range(3):
            cb.record_failure()
        opened_at = cb._opened_at
        assert opened_at is not None

        with patch("chaser.net.client.time.monotonic", return_value=opened_at + 31.0):
            assert cb.state is CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state is CircuitState.OPEN

    def test_reset_clears_all_state(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        cb.reset()
        assert cb.state is CircuitState.CLOSED
        assert cb._failures == 0
        assert cb._opened_at is None


# ---------------------------------------------------------------------------
# NetClient integration tests (respx mocks httpx transport)
# ---------------------------------------------------------------------------


class TestNetClientFetch:
    @respx.mock
    async def test_successful_get(self) -> None:
        respx.get("http://example.com/").mock(
            return_value=httpx.Response(200, content=b"hello world")
        )
        async with NetClient(http2=False) as client:
            resp = await client.fetch(Request("http://example.com/"))

        assert resp.status == 200
        assert resp.body == b"hello world"
        assert resp.ok is True

    @respx.mock
    async def test_response_url_follows_redirects(self) -> None:
        respx.get("http://example.com/old").mock(
            return_value=httpx.Response(200, content=b"")
        )
        async with NetClient(http2=False) as client:
            resp = await client.fetch(Request("http://example.com/old"))

        assert "example.com" in resp.url

    @respx.mock
    async def test_response_headers_mapped(self) -> None:
        respx.get("http://example.com/").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html", "x-custom": "abc"},
                content=b"",
            )
        )
        async with NetClient(http2=False) as client:
            resp = await client.fetch(Request("http://example.com/"))

        assert resp.headers["content-type"] == "text/html"
        assert resp.headers["x-custom"] == "abc"

    @respx.mock
    async def test_request_attached_to_response(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        req = Request("http://example.com/")
        async with NetClient(http2=False) as client:
            resp = await client.fetch(req)

        assert resp.request is req

    @respx.mock
    async def test_elapsed_is_non_negative(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        async with NetClient(http2=False) as client:
            resp = await client.fetch(Request("http://example.com/"))

        assert resp.elapsed >= 0.0

    @respx.mock
    async def test_non_2xx_does_not_raise(self) -> None:
        respx.get("http://example.com/404").mock(return_value=httpx.Response(404, content=b"nope"))
        async with NetClient(http2=False) as client:
            resp = await client.fetch(Request("http://example.com/404"))

        assert resp.status == 404
        assert resp.ok is False

    @respx.mock
    async def test_transport_error_raises_fetch_error(self) -> None:
        respx.get("http://broken.com/").mock(side_effect=httpx.ConnectError("refused"))
        async with NetClient(http2=False) as client:
            with pytest.raises(FetchError):
                await client.fetch(Request("http://broken.com/"))

    def test_requires_context_manager(self) -> None:
        client = NetClient()
        with pytest.raises(RuntimeError):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                client.fetch(Request("http://example.com/"))
            )


class TestNetClientCircuitBreaker:
    @respx.mock
    async def test_circuit_opens_after_threshold(self) -> None:
        respx.get("http://flaky.com/").mock(side_effect=httpx.ConnectError("down"))
        async with NetClient(http2=False, circuit_breaker_threshold=3) as client:
            for _ in range(3):
                with pytest.raises(FetchError):
                    await client.fetch(Request("http://flaky.com/"))

            assert client.circuit_breaker("flaky.com").is_open()

    @respx.mock
    async def test_open_circuit_raises_circuit_open_error(self) -> None:
        respx.get("http://flaky.com/").mock(side_effect=httpx.ConnectError("down"))
        async with NetClient(http2=False, circuit_breaker_threshold=2) as client:
            for _ in range(2):
                with pytest.raises(FetchError):
                    await client.fetch(Request("http://flaky.com/"))

            with pytest.raises(CircuitOpenError):
                await client.fetch(Request("http://flaky.com/"))

    @respx.mock
    async def test_independent_breakers_per_domain(self) -> None:
        respx.get("http://down.com/").mock(side_effect=httpx.ConnectError("down"))
        respx.get("http://up.com/").mock(return_value=httpx.Response(200, content=b"ok"))

        async with NetClient(http2=False, circuit_breaker_threshold=2) as client:
            for _ in range(2):
                with pytest.raises(FetchError):
                    await client.fetch(Request("http://down.com/"))

            # down.com is open — but up.com should work fine
            resp = await client.fetch(Request("http://up.com/"))
            assert resp.status == 200

    @respx.mock
    async def test_circuit_closes_after_recovery(self) -> None:
        respx.get("http://recovering.com/").mock(return_value=httpx.Response(200, content=b"ok"))

        async with NetClient(http2=False, circuit_breaker_threshold=3) as client:
            breaker = client.circuit_breaker("recovering.com")
            # Force open state manually
            for _ in range(3):
                breaker.record_failure()
            assert breaker.is_open()

            opened_at = breaker._opened_at
            assert opened_at is not None
            with patch("chaser.net.client.time.monotonic", return_value=opened_at + 31.0):
                assert not breaker.is_open()  # should be HALF_OPEN now

            resp = await client.fetch(Request("http://recovering.com/"))
            assert resp.status == 200
            assert not breaker.is_open()
