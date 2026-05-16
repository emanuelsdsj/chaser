from __future__ import annotations

import json
from pathlib import Path

from chaser.item.base import Item
from chaser.pipeline.base import Pipeline, Stage
from chaser.pipeline.filters import DuplicateFilter


class _URLItem(Item):
    url: str
    title: str = ""


class _RaisingStage(Stage):
    async def process(self, item: Item) -> Item:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# DuplicateFilter
# ---------------------------------------------------------------------------


class TestDuplicateFilter:
    async def test_first_item_passes(self) -> None:
        f = DuplicateFilter(key=lambda i: i.url)  # type: ignore[attr-defined]
        item = _URLItem(url="https://example.com/a")
        result = await f.process(item)
        assert result is item

    async def test_duplicate_is_dropped(self) -> None:
        f = DuplicateFilter(key=lambda i: i.url)  # type: ignore[attr-defined]
        item = _URLItem(url="https://example.com/a")
        await f.process(item)
        result = await f.process(_URLItem(url="https://example.com/a"))
        assert result is None

    async def test_different_urls_both_pass(self) -> None:
        f = DuplicateFilter(key=lambda i: i.url)  # type: ignore[attr-defined]
        a = _URLItem(url="https://example.com/a")
        b = _URLItem(url="https://example.com/b")
        assert await f.process(a) is a
        assert await f.process(b) is b

    async def test_default_key_deduplicates_by_content(self) -> None:
        f = DuplicateFilter()
        item = _URLItem(url="https://x.com")
        await f.process(item)
        # different Python object, same field values → treated as duplicate by default key
        result = await f.process(_URLItem(url="https://x.com"))
        assert result is None

    async def test_filter_in_pipeline(self) -> None:
        seen: list[Item] = []

        class _Collect(Stage):
            async def process(self, item: Item) -> Item:
                seen.append(item)
                return item

        pipeline = Pipeline([DuplicateFilter(key=lambda i: i.url), _Collect()])  # type: ignore[attr-defined]
        async with pipeline.run():
            for _ in range(3):
                await pipeline.process(_URLItem(url="https://example.com/page"))
            await pipeline.process(_URLItem(url="https://example.com/other"))

        assert len(seen) == 2

    async def test_dedup_is_per_instance(self) -> None:
        f1 = DuplicateFilter(key=lambda i: i.url)  # type: ignore[attr-defined]
        f2 = DuplicateFilter(key=lambda i: i.url)  # type: ignore[attr-defined]
        item = _URLItem(url="https://example.com")
        await f1.process(item)
        # f2 has its own seen set — same item should pass
        result = await f2.process(item)
        assert result is item


# ---------------------------------------------------------------------------
# Dead-letter queue
# ---------------------------------------------------------------------------


class TestDeadLetterQueue:
    async def test_failed_item_written_to_file(self, tmp_path: Path) -> None:
        dlq = tmp_path / "dead.jsonl"
        pipeline = Pipeline([_RaisingStage()], dead_letter=dlq)
        async with pipeline.run():
            result = await pipeline.process(_URLItem(url="https://example.com"))

        assert result is None
        lines = dlq.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["stage"] == "_RaisingStage"
        assert "boom" in entry["error"]
        assert entry["item"]["url"] == "https://example.com"
        assert "timestamp" in entry

    async def test_multiple_failures_appended(self, tmp_path: Path) -> None:
        dlq = tmp_path / "dead.jsonl"
        pipeline = Pipeline([_RaisingStage()], dead_letter=dlq)
        async with pipeline.run():
            for i in range(3):
                await pipeline.process(_URLItem(url=f"https://example.com/{i}"))

        lines = dlq.read_text().strip().splitlines()
        assert len(lines) == 3

    async def test_no_dead_letter_file_without_param(self, tmp_path: Path) -> None:
        pipeline = Pipeline([_RaisingStage()])
        async with pipeline.run():
            await pipeline.process(_URLItem(url="https://example.com"))
        # no file created — no crash
        assert not any(tmp_path.iterdir())

    async def test_successful_items_not_written(self, tmp_path: Path) -> None:
        dlq = tmp_path / "dead.jsonl"

        class _PassStage(Stage):
            async def process(self, item: Item) -> Item:
                return item

        pipeline = Pipeline([_PassStage()], dead_letter=dlq)
        async with pipeline.run():
            await pipeline.process(_URLItem(url="https://example.com"))

        assert not dlq.exists()

    async def test_dead_letter_accepts_string_path(self, tmp_path: Path) -> None:
        dlq = str(tmp_path / "dead.jsonl")
        pipeline = Pipeline([_RaisingStage()], dead_letter=dlq)
        async with pipeline.run():
            await pipeline.process(_URLItem(url="https://x.com"))

        assert Path(dlq).exists()
