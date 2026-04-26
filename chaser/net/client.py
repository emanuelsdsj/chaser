from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, Any

import httpx

from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response

if TYPE_CHECKING:
    from chaser.hooks.base import FetchHook


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Three-state circuit breaker for a single host.

    Transitions:
      CLOSED  → OPEN      after ``failure_threshold`` consecutive failures
      OPEN    → HALF_OPEN after ``recovery_timeout`` seconds have elapsed
      HALF_OPEN → CLOSED  on the first successful request
      HALF_OPEN → OPEN    on any failure (resets the recovery clock)
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and self._opened_at is not None
            and time.monotonic() - self._opened_at >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def is_open(self) -> bool:
        return self.state is CircuitState.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()

    def reset(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None


class CircuitOpenError(Exception):
    """Request blocked because the host's circuit breaker is open."""


class FetchError(Exception):
    """Transport-level failure (connection refused, timeout, etc.)."""


class NetClient:
    """Async HTTP client with connection pooling, HTTP/2, and per-domain circuit breakers.

    Usage::

        async with NetClient() as client:
            response = await client.fetch(Request("https://example.com"))

    Proxy: pass any proxy URL understood by httpx — http://, https://, or
    socks5:// (requires httpx-socks installed as a transport).
    """

    def __init__(
        self,
        *,
        http2: bool = True,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_keepalive: int = 20,
        proxy: str | None = None,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_recovery: float = 30.0,
        follow_redirects: bool = True,
        verify: bool = True,
        hooks: list[FetchHook] | None = None,
    ) -> None:
        self._http2 = http2
        self._timeout = timeout
        self._proxy = proxy
        self._follow_redirects = follow_redirects
        self._verify = verify
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
        )
        self._cb_threshold = circuit_breaker_threshold
        self._cb_recovery = circuit_breaker_recovery
        self._breakers: dict[str, CircuitBreaker] = {}
        self._client: httpx.AsyncClient | None = None
        self._hooks: list[FetchHook] = hooks or []

    def _make_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "http2": self._http2,
            "timeout": self._timeout,
            "limits": self._limits,
            "follow_redirects": self._follow_redirects,
            "verify": self._verify,
        }
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return httpx.AsyncClient(**kwargs)

    def _breaker_for(self, host: str) -> CircuitBreaker:
        if host not in self._breakers:
            self._breakers[host] = CircuitBreaker(
                failure_threshold=self._cb_threshold,
                recovery_timeout=self._cb_recovery,
            )
        return self._breakers[host]

    async def __aenter__(self) -> NetClient:
        self._client = self._make_client()
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*args)
            self._client = None

    async def fetch(self, request: Request) -> Response:
        if self._client is None:
            raise RuntimeError("NetClient must be used as an async context manager")

        for hook in self._hooks:
            request = await hook.before_request(request)

        host = httpx.URL(request.url).host
        breaker = self._breaker_for(host)

        if breaker.is_open():
            raise CircuitOpenError(f"Circuit open for {host!r} — request skipped")

        t0 = time.monotonic()
        try:
            raw = await self._client.request(
                method=request.method,
                url=request.url,
                headers=dict(request.headers),
                content=request.body,
            )
        except httpx.TransportError as exc:
            breaker.record_failure()
            raise FetchError(str(exc)) from exc

        elapsed = time.monotonic() - t0
        breaker.record_success()

        encoding = raw.encoding or "utf-8"
        response = Response(
            url=str(raw.url),
            status=raw.status_code,
            headers=Headers(dict(raw.headers)),
            body=raw.content,
            encoding=encoding,
            elapsed=elapsed,
            request=request,
        )

        for hook in self._hooks:
            response = await hook.after_response(response)

        return response

    def circuit_breaker(self, host: str) -> CircuitBreaker:
        """Expose the breaker for a given host (useful for monitoring/testing)."""
        return self._breaker_for(host)
