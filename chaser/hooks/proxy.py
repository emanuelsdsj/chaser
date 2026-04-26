from __future__ import annotations

import itertools
import logging

logger = logging.getLogger(__name__)


class ProxyPool:
    """Round-robin proxy pool with per-proxy failure tracking.

    Proxies with too many consecutive failures are skipped until one
    succeeds and resets the counter. All proxies unhealthy → ``next()``
    returns ``None``.

    Usage::

        pool = ProxyPool(["http://p1:8080", "socks5://p2:1080"])
        proxy = pool.next()         # None if all proxies are dead
        if proxy:
            async with NetClient(proxy=proxy) as client:
                response = await client.fetch(req)
            pool.mark_success(proxy)
        else:
            pool.mark_failure(proxy)
    """

    def __init__(self, proxies: list[str], max_failures: int = 3) -> None:
        if not proxies:
            raise ValueError("ProxyPool requires at least one proxy URL")
        self._proxies = list(proxies)
        self._max_failures = max_failures
        self._failures: dict[str, int] = {p: 0 for p in proxies}
        self._cycle = itertools.cycle(self._proxies)

    def next(self) -> str | None:
        """Return the next healthy proxy or ``None`` when all are exhausted."""
        for _ in range(len(self._proxies)):
            proxy = next(self._cycle)
            if self._failures[proxy] < self._max_failures:
                return proxy
        return None

    def mark_success(self, proxy: str) -> None:
        if proxy in self._failures:
            self._failures[proxy] = 0

    def mark_failure(self, proxy: str) -> None:
        if proxy in self._failures:
            self._failures[proxy] += 1
            logger.warning(
                "Proxy %r failed (%d/%d)", proxy, self._failures[proxy], self._max_failures
            )

    def healthy_count(self) -> int:
        return sum(1 for f in self._failures.values() if f < self._max_failures)
