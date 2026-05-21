from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from chaser.frontier.sqlite import SqliteFrontier
from chaser.net.request import Request


def _req(url: str, priority: int = 0, callback: str | None = None) -> Request:
    return Request(url=url, priority=priority, callback=callback)


def _make(tmp_path: Path, strategy: str = "bfs") -> SqliteFrontier:
    f = SqliteFrontier(tmp_path / "frontier.db", strategy=strategy)
    f.open()
    return f


# ---------------------------------------------------------------------------
# basic push / pop / task_done flow
# ---------------------------------------------------------------------------


class TestBasicFlow:
    async def test_new_url_accepted(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            accepted = await f.push(_req("https://a.com"))
            assert accepted is True
        finally:
            f.close()

    async def test_duplicate_url_rejected(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            await f.push(_req("https://a.com"))
            second = await f.push(_req("https://a.com"))
            assert second is False
        finally:
            f.close()

    async def test_seen_count_tracks_unique_urls(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            assert f.seen_count == 0
            await f.push(_req("https://a.com"))
            await f.push(_req("https://b.com"))
            await f.push(_req("https://a.com"))  # dupe
            assert f.seen_count == 2
        finally:
            f.close()

    async def test_seen_returns_correct_values(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            assert f.seen("https://a.com") is False
            await f.push(_req("https://a.com"))
            assert f.seen("https://a.com") is True
        finally:
            f.close()

    async def test_pop_returns_correct_request(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            req = _req("https://a.com", callback="parse")
            await f.push(req)
            got = await f.pop()
            assert got.url == "https://a.com"
            assert got.callback == "parse"
            f.task_done()
            await f.join()
        finally:
            f.close()

    async def test_empty_and_qsize(self, tmp_path: Path) -> None:
        f = _make(tmp_path)
        try:
            assert f.empty() is True
            assert f.qsize() == 0
            await f.push(_req("https://a.com"))
            assert f.empty() is False
            assert f.qsize() == 1
            await f.pop()
            assert f.empty() is True
            f.task_done()
        finally:
            f.close()


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    async def test_seen_urls_survive_close_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))
        f.close()

        # reopen — same DB
        f2 = SqliteFrontier(db)
        f2.open()
        try:
            assert f2.seen_count == 2
            assert f2.seen("https://a.com") is True
            assert f2.seen("https://b.com") is True
            assert f2.seen("https://c.com") is False
        finally:
            f2.close()

    async def test_pending_requests_reloaded(self, tmp_path: Path) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))
        f.close()

        f2 = SqliteFrontier(db)
        f2.open()
        try:
            assert f2.qsize() == 2
            r1 = await f2.pop()
            r2 = await f2.pop()
            urls = {r1.url, r2.url}
            assert urls == {"https://a.com", "https://b.com"}
            f2.task_done()
            f2.task_done()
            await f2.join()
        finally:
            f2.close()

    async def test_no_resume_log_when_fresh(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="chaser.frontier.sqlite"):
            f = SqliteFrontier(tmp_path / "fresh.db")
            f.open()
            f.close()
        assert not any("Resuming" in r.message for r in caplog.records)

    async def test_resume_log_when_pending_exist(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        await f.push(_req("https://a.com"))
        f.close()

        with caplog.at_level(logging.INFO, logger="chaser.frontier.sqlite"):
            f2 = SqliteFrontier(db)
            f2.open()
            f2.close()
        assert any("Resuming" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# crash recovery — in_flight → pending on reopen
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    async def test_inflight_becomes_pending_after_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))

        # pop one — it's now in_flight in the DB
        _r = await f.pop()

        # simulate crash: close without task_done
        f.close()

        # reopen — that in_flight request should come back as pending
        f2 = SqliteFrontier(db)
        f2.open()
        try:
            assert f2.qsize() == 2  # both should be pending again
            r1 = await f2.pop()
            r2 = await f2.pop()
            urls = {r1.url, r2.url}
            assert urls == {"https://a.com", "https://b.com"}
            f2.task_done()
            f2.task_done()
            await f2.join()
        finally:
            f2.close()

    async def test_completed_requests_not_replayed(self, tmp_path: Path) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        await f.push(_req("https://a.com"))
        await f.push(_req("https://b.com"))

        # properly complete one
        r = await f.pop()
        assert r.url == "https://a.com"
        f.task_done()
        await asyncio.sleep(0)  # let queue internals settle

        # "crash" with one still pending
        f.close()

        f2 = SqliteFrontier(db)
        f2.open()
        try:
            assert f2.qsize() == 1
            r2 = await f2.pop()
            assert r2.url == "https://b.com"
            f2.task_done()
            await f2.join()
        finally:
            f2.close()


# ---------------------------------------------------------------------------
# ordering strategies
# ---------------------------------------------------------------------------


class TestOrdering:
    async def test_bfs_is_fifo(self, tmp_path: Path) -> None:
        f = _make(tmp_path, strategy="bfs")
        try:
            urls = [f"https://example.com/page/{i}" for i in range(4)]
            for url in urls:
                await f.push(_req(url))
            popped = [await f.pop() for _ in urls]
            for _p in popped:
                f.task_done()
            assert [r.url for r in popped] == urls
        finally:
            f.close()

    async def test_dfs_is_lifo(self, tmp_path: Path) -> None:
        f = _make(tmp_path, strategy="dfs")
        try:
            urls = [f"https://example.com/page/{i}" for i in range(4)]
            for url in urls:
                await f.push(_req(url))
            popped = [await f.pop() for _ in urls]
            for _p in popped:
                f.task_done()
            assert [r.url for r in popped] == list(reversed(urls))
        finally:
            f.close()

    async def test_score_higher_priority_first(self, tmp_path: Path) -> None:
        f = _make(tmp_path, strategy="score")
        try:
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
        finally:
            f.close()


# ---------------------------------------------------------------------------
# request fields survive the round-trip through the DB
# ---------------------------------------------------------------------------


class TestRoundTrip:
    async def test_request_fields_preserved(self, tmp_path: Path) -> None:
        db = tmp_path / "crawl.db"
        f = SqliteFrontier(db)
        f.open()
        req = Request(
            url="https://example.com",
            method="POST",
            headers={"x-token": "secret"},
            body=b"\x00binary\xff",
            meta={"trapper": "my_trapper", "depth": 3},
            priority=7,
            callback="parse_detail",
            use_browser=True,
        )
        await f.push(req)
        f.close()

        f2 = SqliteFrontier(db)
        f2.open()
        try:
            r = await f2.pop()
            f2.task_done()
            assert r.url == req.url
            assert r.method == req.method
            assert r.headers["x-token"] == "secret"
            assert r.body == b"\x00binary\xff"
            assert r.meta == {"trapper": "my_trapper", "depth": 3}
            assert r.priority == 7
            assert r.callback == "parse_detail"
            assert r.use_browser is True
        finally:
            f2.close()
