from __future__ import annotations

import asyncio
import logging

import fakeredis.aioredis as fake
import pytest

from chaser.frontier.redis_frontier import RedisFrontier
from chaser.net.request import Request


def _req(url: str, priority: int = 0, callback: str | None = None) -> Request:
    return Request(url=url, priority=priority, callback=callback)


def _make(strategy: str = "bfs", sort_params: bool = False, clear: bool = False) -> RedisFrontier:
    """Build a RedisFrontier wired to a fresh in-process FakeRedis server."""
    server = fake.FakeServer()
    r = fake.FakeRedis(server=server, decode_responses=True)
    f = RedisFrontier(strategy=strategy, sort_params=sort_params, clear=clear)
    f._redis = r
    return f


def _make_on(server: fake.FakeServer, **kwargs: object) -> RedisFrontier:
    """Build a RedisFrontier sharing an existing FakeServer (multi-instance tests)."""
    r = fake.FakeRedis(server=server, decode_responses=True)
    f = RedisFrontier(**kwargs)  # type: ignore[arg-type]
    f._redis = r
    return f


async def _open(f: RedisFrontier) -> RedisFrontier:
    """Open the frontier without a real Redis connection (client already injected)."""
    await f.open()
    return f


async def _make_open(strategy: str = "bfs") -> RedisFrontier:
    return await _open(_make(strategy=strategy))


# ---------------------------------------------------------------------------
# basic push / pop / task_done flow
# ---------------------------------------------------------------------------


class TestBasicFlow:
    async def test_new_url_accepted(self) -> None:
        f = await _make_open()
        assert await f.push(_req("https://a.com")) is True

    async def test_duplicate_url_rejected(self) -> None:
        f = await _make_open()
        await f.push(_req("https://a.com"))
        assert await f.push(_req("https://a.com")) is False

    async def test_seen_count_tracks_unique_urls(self) -> None:
        f = await _make_open()
        assert f.seen_count == 0
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))
        await f.push(_req("https://a.com"))  # dupe
        assert f.seen_count == 2

    async def test_seen_async_returns_correct_values(self) -> None:
        f = await _make_open()
        assert await f.seen_async("https://a.com") is False
        await f.push(_req("https://a.com"))
        assert await f.seen_async("https://a.com") is True
        assert await f.seen_async("https://b.com") is False

    async def test_seen_raises(self) -> None:
        f = await _make_open()
        with pytest.raises(RuntimeError, match="seen_async"):
            f.seen("https://a.com")

    async def test_pop_returns_correct_request(self) -> None:
        f = await _make_open()
        req = _req("https://a.com", callback="parse_detail")
        await f.push(req)
        got = await f.pop()
        assert got.url == "https://a.com"
        assert got.callback == "parse_detail"
        f.task_done()
        await f.join()

    async def test_empty_and_qsize(self) -> None:
        f = await _make_open()
        assert f.empty() is True
        assert f.qsize() == 0
        await f.push(_req("https://a.com"))
        assert f.empty() is False
        assert f.qsize() == 1
        await f.pop()
        assert f.qsize() == 0
        f.task_done()

    async def test_fragment_stripped(self) -> None:
        f = await _make_open()
        await f.push(_req("https://a.com/page#section"))
        # same URL without fragment should be considered a duplicate
        dup = await f.push(_req("https://a.com/page"))
        assert dup is False


# ---------------------------------------------------------------------------
# ordering strategies
# ---------------------------------------------------------------------------


class TestOrdering:
    async def test_bfs_is_fifo(self) -> None:
        f = await _make_open(strategy="bfs")
        urls = [f"https://example.com/page/{i}" for i in range(4)]
        for url in urls:
            await f.push(_req(url))
        popped = [await f.pop() for _ in urls]
        for _ in popped:
            f.task_done()
        assert [r.url for r in popped] == urls

    async def test_dfs_is_lifo(self) -> None:
        f = await _make_open(strategy="dfs")
        urls = [f"https://example.com/page/{i}" for i in range(4)]
        for url in urls:
            await f.push(_req(url))
        popped = [await f.pop() for _ in urls]
        for _ in popped:
            f.task_done()
        assert [r.url for r in popped] == list(reversed(urls))

    async def test_score_higher_priority_first(self) -> None:
        f = await _make_open(strategy="score")
        await f.push(_req("https://low.com", priority=1))
        await f.push(_req("https://high.com", priority=10))
        await f.push(_req("https://mid.com", priority=5))
        first = await f.pop()
        second = await f.pop()
        third = await f.pop()
        for _ in range(3):
            f.task_done()
        assert first.url == "https://high.com"
        assert second.url == "https://mid.com"
        assert third.url == "https://low.com"


# ---------------------------------------------------------------------------
# request fields survive the round-trip through Redis
# ---------------------------------------------------------------------------


class TestRoundTrip:
    async def test_all_fields_preserved(self) -> None:
        f = await _make_open()
        from chaser.net.headers import Headers

        req = Request(
            url="https://example.com",
            method="POST",
            headers=Headers({"x-token": "secret"}),
            body=b"\x00binary\xff",
            meta={"trapper": "mine", "depth": 3},
            priority=7,
            callback="parse_detail",
            use_browser=True,
        )
        await f.push(req)
        got = await f.pop()
        f.task_done()

        assert got.url == req.url
        assert got.method == req.method
        assert got.headers["x-token"] == "secret"
        assert got.body == b"\x00binary\xff"
        assert got.meta == {"trapper": "mine", "depth": 3}
        assert got.priority == 7
        assert got.callback == "parse_detail"
        assert got.use_browser is True


# ---------------------------------------------------------------------------
# crash recovery
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    async def test_inflight_becomes_pending_after_reopen(self) -> None:
        server = fake.FakeServer()
        f1 = await _open(_make_on(server))

        await f1.push(_req("https://a.com"))
        await f1.push(_req("https://b.com"))

        # pop one — it's now in inflight hash
        _r = await f1.pop()
        assert await f1._redis.hlen(f1._key_inflight) == 1

        # "crash": open a new frontier on same server without calling task_done
        f2 = await _open(_make_on(server))

        # both items should be back in queue
        assert f2._queue_size_hint == 2
        assert await f2._redis.hlen(f2._key_inflight) == 0

        r1 = await f2.pop()
        r2 = await f2.pop()
        urls = {r1.url, r2.url}
        assert urls == {"https://a.com", "https://b.com"}
        f2.task_done()
        f2.task_done()
        await f2.join()

    async def test_seen_urls_survive_reopen(self) -> None:
        server = fake.FakeServer()
        f1 = await _open(_make_on(server))
        await f1.push(_req("https://a.com"))
        await f1.push(_req("https://b.com"))

        f2 = await _open(_make_on(server))
        assert f2.seen_count == 2
        assert await f2.seen_async("https://a.com") is True
        assert await f2.seen_async("https://c.com") is False

    async def test_completed_requests_not_replayed(self) -> None:
        server = fake.FakeServer()
        f1 = await _open(_make_on(server))
        await f1.push(_req("https://a.com"))
        await f1.push(_req("https://b.com"))

        req = await f1.pop()
        assert req.url == "https://a.com"
        f1.task_done()
        await asyncio.sleep(0)  # let the hdel task run

        f2 = await _open(_make_on(server))
        assert f2._queue_size_hint == 1
        r2 = await f2.pop()
        assert r2.url == "https://b.com"
        f2.task_done()
        await f2.join()


# ---------------------------------------------------------------------------
# join() drains properly
# ---------------------------------------------------------------------------


class TestJoin:
    async def test_join_returns_when_all_done(self) -> None:
        f = await _make_open()
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))

        async def worker() -> None:
            for _ in range(2):
                _req_obj = await f.pop()
                await asyncio.sleep(0)
                f.task_done()

        task = asyncio.create_task(worker())
        await asyncio.wait_for(f.join(), timeout=5.0)
        await task

    async def test_join_waits_for_slow_worker(self) -> None:
        """join() should not return while a worker has an item in flight."""
        f = await _make_open()
        await f.push(_req("https://a.com"))
        done = False

        async def slow_worker() -> None:
            nonlocal done
            await f.pop()
            await asyncio.sleep(0.1)  # simulate slow processing
            f.task_done()
            done = True

        task = asyncio.create_task(slow_worker())
        await asyncio.wait_for(f.join(), timeout=5.0)
        assert done is True
        await task


# ---------------------------------------------------------------------------
# clear=True wipes state
# ---------------------------------------------------------------------------


class TestClear:
    async def test_clear_wipes_all_keys(self) -> None:
        server = fake.FakeServer()
        f1 = await _open(_make_on(server))
        await f1.push(_req("https://a.com"))

        # clear=True removes all frontier keys
        f2 = await _open(_make_on(server, clear=True))
        assert await f2._redis.zcard(f2._key_queue) == 0
        assert await f2._redis.hlen(f2._key_seen) == 0


# ---------------------------------------------------------------------------
# resume log
# ---------------------------------------------------------------------------


class TestLogging:
    async def test_resume_log_when_pending_exist(self, caplog: pytest.LogCaptureFixture) -> None:
        server = fake.FakeServer()
        f1 = await _open(_make_on(server))
        await f1.push(_req("https://a.com"))

        with caplog.at_level(logging.INFO, logger="chaser.frontier.redis_frontier"):
            await _open(_make_on(server))

        assert any("resuming" in r.message.lower() for r in caplog.records)

    async def test_no_resume_log_when_fresh(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="chaser.frontier.redis_frontier"):
            await _make_open()

        assert not any("resuming" in r.message.lower() for r in caplog.records)
