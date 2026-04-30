from __future__ import annotations

import time

import httpx
import pytest
import respx

from chaser.engine.runner import Engine
from chaser.engine.stats import CrawlStats
from chaser.item.base import Item
from chaser.net.response import Response
from chaser.trapper.base import Trapper


class _PageItem(Item):
    url: str


class _SimpleTrpper(Trapper):
    name = "simple"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        yield _PageItem(url=response.url)


class _NoItemTrpper(Trapper):
    name = "noitem"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# CrawlStats unit tests
# ---------------------------------------------------------------------------


def test_stats_defaults() -> None:
    s = CrawlStats()
    assert s.requests_sent == 0
    assert s.requests_ok == 0
    assert s.requests_failed == 0
    assert s.items_scraped == 0
    assert s.bytes_downloaded == 0


def test_stats_elapsed_grows() -> None:
    s = CrawlStats()
    t0 = s.elapsed
    time.sleep(0.01)
    assert s.elapsed > t0


def test_stats_elapsed_frozen_after_finish() -> None:
    s = CrawlStats()
    time.sleep(0.01)
    s._mark_finished()
    elapsed_at_finish = s.elapsed
    time.sleep(0.02)
    assert s.elapsed == pytest.approx(elapsed_at_finish, abs=1e-6)


def test_stats_requests_per_second_zero_when_no_time() -> None:
    s = CrawlStats()
    s._mark_finished()
    # elapsed ≈ 0 → rps should not raise
    assert s.requests_per_second >= 0.0


def test_stats_requests_per_second_nonzero() -> None:
    s = CrawlStats()
    s.requests_sent = 10
    time.sleep(0.01)
    s._mark_finished()
    assert s.requests_per_second > 0


def test_stats_repr_shows_key_fields() -> None:
    s = CrawlStats(requests_sent=5, items_scraped=3)
    r = repr(s)
    assert "requests_sent=5" in r
    assert "items_scraped=3" in r
    assert "elapsed=" in r


# ---------------------------------------------------------------------------
# Engine stats integration
# ---------------------------------------------------------------------------


@respx.mock
async def test_stats_requests_sent_and_ok() -> None:
    respx.get("http://a.com/").mock(return_value=httpx.Response(200, content=b"hello"))

    engine = Engine(concurrency=1, http2=False)
    await engine.run(_SimpleTrpper(["http://a.com/"]))

    assert engine.stats.requests_sent == 1
    assert engine.stats.requests_ok == 1
    assert engine.stats.requests_failed == 0


@respx.mock
async def test_stats_items_scraped() -> None:
    for i in range(3):
        respx.get(f"http://page{i}.com/").mock(return_value=httpx.Response(200, content=b"x"))

    engine = Engine(concurrency=3, http2=False)
    await engine.run(_SimpleTrpper([f"http://page{i}.com/" for i in range(3)]))

    assert engine.stats.items_scraped == 3


@respx.mock
async def test_stats_failed_incremented_on_network_error() -> None:
    respx.get("http://broken.com/").mock(side_effect=httpx.ConnectError("refused"))

    engine = Engine(concurrency=1, http2=False)
    await engine.run(_SimpleTrpper(["http://broken.com/"]))

    assert engine.stats.requests_sent == 1
    assert engine.stats.requests_failed == 1
    assert engine.stats.requests_ok == 0


@respx.mock
async def test_stats_bytes_downloaded() -> None:
    body = b"a" * 100
    respx.get("http://a.com/").mock(return_value=httpx.Response(200, content=body))

    engine = Engine(concurrency=1, http2=False)
    await engine.run(_NoItemTrpper(["http://a.com/"]))

    assert engine.stats.bytes_downloaded == 100


@respx.mock
async def test_stats_reset_between_runs() -> None:
    respx.get("http://a.com/").mock(return_value=httpx.Response(200, content=b"x"))

    engine = Engine(concurrency=1, http2=False)
    await engine.run(_SimpleTrpper(["http://a.com/"]))
    first_sent = engine.stats.requests_sent

    respx.get("http://a.com/").mock(return_value=httpx.Response(200, content=b"x"))
    await engine.run(_SimpleTrpper(["http://a.com/"]))

    assert engine.stats.requests_sent == first_sent  # reset, not accumulated


@respx.mock
async def test_stats_elapsed_positive_after_run() -> None:
    respx.get("http://a.com/").mock(return_value=httpx.Response(200, content=b"x"))

    engine = Engine(concurrency=1, http2=False)
    await engine.run(_SimpleTrpper(["http://a.com/"]))

    assert engine.stats.elapsed > 0


async def test_stats_empty_crawl_marks_finish() -> None:
    engine = Engine(concurrency=1, http2=False)
    await engine.run(_SimpleTrpper([]))

    assert engine.stats.elapsed >= 0
    assert engine.stats._finish is not None
