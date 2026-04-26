from __future__ import annotations

import pytest

from chaser.frontier.queue import BloomFilter, Frontier
from chaser.net.request import Request

# ---------------------------------------------------------------------------
# BloomFilter
# ---------------------------------------------------------------------------


class TestBloomFilter:
    def test_unseen_item_not_in_filter(self) -> None:
        bf = BloomFilter(capacity=1000)
        assert "http://example.com" not in bf

    def test_added_item_detected(self) -> None:
        bf = BloomFilter(capacity=1000)
        bf.add("http://example.com")
        assert "http://example.com" in bf

    def test_multiple_items(self) -> None:
        bf = BloomFilter(capacity=1000)
        urls = [f"http://example.com/page/{i}" for i in range(100)]
        for url in urls:
            bf.add(url)
        for url in urls:
            assert url in bf

    def test_len_tracks_insertions(self) -> None:
        bf = BloomFilter(capacity=1000)
        assert len(bf) == 0
        bf.add("a")
        bf.add("b")
        bf.add("c")
        assert len(bf) == 3

    def test_false_positive_rate_within_bounds(self) -> None:
        capacity = 10_000
        error_rate = 0.01
        bf = BloomFilter(capacity=capacity, error_rate=error_rate)

        for i in range(capacity):
            bf.add(f"http://seen.com/page/{i}")

        false_positives = sum(1 for i in range(capacity) if f"http://unseen.com/item/{i}" in bf)
        actual_fpr = false_positives / capacity
        # Allow 3× the declared rate as headroom — still many orders of magnitude from random
        assert actual_fpr <= error_rate * 3, f"FPR too high: {actual_fpr:.4f}"

    def test_estimated_fpr_zero_when_empty(self) -> None:
        bf = BloomFilter(capacity=1000)
        assert bf.estimated_fpr == 0.0

    def test_estimated_fpr_grows_with_insertions(self) -> None:
        bf = BloomFilter(capacity=100, error_rate=0.01)
        fpr_before = bf.estimated_fpr
        for i in range(50):
            bf.add(str(i))
        assert bf.estimated_fpr > fpr_before

    def test_non_string_not_in_filter(self) -> None:
        bf = BloomFilter(capacity=100)
        bf.add("hello")
        assert 42 not in bf  # type: ignore[operator]

    def test_invalid_error_rate_raises(self) -> None:
        with pytest.raises(ValueError):
            BloomFilter(capacity=100, error_rate=0.0)
        with pytest.raises(ValueError):
            BloomFilter(capacity=100, error_rate=1.0)

    def test_invalid_capacity_raises(self) -> None:
        with pytest.raises(ValueError):
            BloomFilter(capacity=0)


# ---------------------------------------------------------------------------
# Frontier
# ---------------------------------------------------------------------------


def _req(url: str, priority: int = 0) -> Request:
    return Request(url=url, priority=priority)


class TestFrontierDedup:
    async def test_new_url_accepted(self) -> None:
        f = Frontier()
        accepted = await f.push(_req("http://a.com"))
        assert accepted is True

    async def test_duplicate_url_rejected(self) -> None:
        f = Frontier()
        await f.push(_req("http://a.com"))
        second = await f.push(_req("http://a.com"))
        assert second is False

    async def test_seen_returns_true_after_push(self) -> None:
        f = Frontier()
        assert f.seen("http://a.com") is False
        await f.push(_req("http://a.com"))
        assert f.seen("http://a.com") is True

    async def test_seen_count_increments(self) -> None:
        f = Frontier()
        assert f.seen_count == 0
        await f.push(_req("http://a.com"))
        await f.push(_req("http://b.com"))
        await f.push(_req("http://a.com"))  # dupe, not counted
        assert f.seen_count == 2

    async def test_qsize_reflects_queue_depth(self) -> None:
        f = Frontier()
        assert f.qsize() == 0
        await f.push(_req("http://a.com"))
        await f.push(_req("http://b.com"))
        assert f.qsize() == 2


class TestFrontierBFS:
    async def test_bfs_is_fifo(self) -> None:
        f = Frontier(strategy="bfs")
        urls = [f"http://example.com/page/{i}" for i in range(5)]
        for url in urls:
            await f.push(_req(url))

        popped = [await f.pop() for _ in urls]
        assert [r.url for r in popped] == urls


class TestFrontierDFS:
    async def test_dfs_is_lifo(self) -> None:
        f = Frontier(strategy="dfs")
        urls = [f"http://example.com/page/{i}" for i in range(5)]
        for url in urls:
            await f.push(_req(url))

        popped = [await f.pop() for _ in urls]
        assert [r.url for r in popped] == list(reversed(urls))


class TestFrontierScore:
    async def test_score_higher_priority_first(self) -> None:
        f = Frontier(strategy="score")
        await f.push(_req("http://low.com", priority=1))
        await f.push(_req("http://high.com", priority=10))
        await f.push(_req("http://mid.com", priority=5))

        first = await f.pop()
        second = await f.pop()
        third = await f.pop()

        assert first.url == "http://high.com"
        assert second.url == "http://mid.com"
        assert third.url == "http://low.com"

    async def test_score_equal_priority_stable(self) -> None:
        f = Frontier(strategy="score")
        await f.push(_req("http://a.com", priority=5))
        await f.push(_req("http://b.com", priority=5))

        # Both have equal priority — insertion order should be preserved as tiebreaker
        first = await f.pop()
        second = await f.pop()
        assert first.url == "http://a.com"
        assert second.url == "http://b.com"


class TestFrontierState:
    async def test_empty_when_nothing_pushed(self) -> None:
        f = Frontier()
        assert f.empty() is True

    async def test_not_empty_after_push(self) -> None:
        f = Frontier()
        await f.push(_req("http://a.com"))
        assert f.empty() is False

    async def test_empty_after_all_popped(self) -> None:
        f = Frontier()
        await f.push(_req("http://a.com"))
        await f.pop()
        assert f.empty() is True

    async def test_task_done_and_join(self) -> None:
        f = Frontier()
        await f.push(_req("http://a.com"))
        await f.pop()
        f.task_done()
        await f.join()  # should not block
