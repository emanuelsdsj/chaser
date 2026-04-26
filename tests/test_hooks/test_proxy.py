from __future__ import annotations

import pytest

from chaser.hooks.proxy import ProxyPool


class TestProxyPool:
    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            ProxyPool([])

    def test_round_robin_cycles_through_all_proxies(self) -> None:
        pool = ProxyPool(["http://p1", "http://p2", "http://p3"])
        selected = [pool.next() for _ in range(6)]
        assert set(selected) == {"http://p1", "http://p2", "http://p3"}

    def test_skips_proxies_at_failure_threshold(self) -> None:
        pool = ProxyPool(["http://bad", "http://good"], max_failures=2)
        pool.mark_failure("http://bad")
        pool.mark_failure("http://bad")  # now at threshold — unhealthy
        for _ in range(6):
            assert pool.next() == "http://good"

    def test_mark_success_resets_failure_counter(self) -> None:
        pool = ProxyPool(["http://p1"], max_failures=3)
        pool.mark_failure("http://p1")
        pool.mark_failure("http://p1")
        pool.mark_success("http://p1")
        assert pool._failures["http://p1"] == 0

    def test_returns_none_when_all_proxies_exhausted(self) -> None:
        pool = ProxyPool(["http://p1", "http://p2"], max_failures=1)
        pool.mark_failure("http://p1")
        pool.mark_failure("http://p2")
        assert pool.next() is None

    def test_healthy_count(self) -> None:
        pool = ProxyPool(["http://p1", "http://p2", "http://p3"], max_failures=2)
        pool.mark_failure("http://p1")
        pool.mark_failure("http://p1")  # now unhealthy
        assert pool.healthy_count() == 2
