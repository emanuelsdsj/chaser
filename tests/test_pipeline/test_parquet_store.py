from __future__ import annotations

import sys
from pathlib import Path

import pytest

from chaser.item.base import Item
from chaser.pipeline.store.parquet import ParquetStore

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


class _ArticleItem(Item):
    url: str
    title: str
    score: int = 0


class _ProductItem(Item):
    name: str
    price: float
    available: bool = True


def _read(path: Path) -> list[dict]:
    table = pq.read_table(path)
    return table.to_pylist()


class TestParquetStore:
    async def test_writes_item_to_parquet(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path)
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="Hello", score=3))
        await store.close()

        rows = _read(path)
        assert len(rows) == 1
        assert rows[0] == {"url": "http://a.com", "title": "Hello", "score": 3}

    async def test_multiple_items_all_written(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path)
        await store.open()
        for i in range(5):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
        await store.close()

        rows = _read(path)
        assert len(rows) == 5
        assert rows[2]["score"] == 2

    async def test_passes_item_through(self, tmp_path: Path) -> None:
        store = ParquetStore(tmp_path / "out.parquet")
        await store.open()
        item = _ArticleItem(url="http://a.com", title="A")
        result = await store.process(item)
        await store.close()
        assert result is item

    async def test_no_write_when_not_opened(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path)
        # process without open — should silently skip, not crash
        result = await store.process(_ArticleItem(url="http://a.com", title="A"))
        assert result.url == "http://a.com"
        assert not path.exists()

    async def test_row_group_flush_at_threshold(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path, row_group_size=3)
        await store.open()
        for i in range(3):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}"))
        # exactly at threshold — writer should exist after process() call
        assert store._writer is not None
        await store.close()

        rows = _read(path)
        assert len(rows) == 3

    async def test_close_flushes_partial_buffer(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path, row_group_size=10)
        await store.open()
        # write fewer items than row_group_size — only flushed on close
        for i in range(4):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}"))
        assert store._writer is None  # not yet flushed mid-stream
        await store.close()

        rows = _read(path)
        assert len(rows) == 4

    async def test_multiple_row_groups_written(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path, row_group_size=3)
        await store.open()
        for i in range(7):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
        await store.close()

        table = pq.read_table(path)
        assert table.num_rows == 7
        # two full groups (3+3) + partial (1) → 3 row groups
        assert pq.read_metadata(path).num_row_groups == 3

    async def test_schema_inferred_from_first_flush(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path, row_group_size=2)
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="A", score=1))
        await store.process(_ArticleItem(url="http://b.com", title="B", score=2))
        await store.close()

        schema = pq.read_schema(path)
        assert set(schema.names) == {"url", "title", "score"}

    async def test_field_types_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path)
        await store.open()
        await store.process(_ProductItem(name="Widget", price=9.99, available=False))
        await store.close()

        rows = _read(path)
        assert rows[0]["name"] == "Widget"
        assert abs(rows[0]["price"] - 9.99) < 1e-6
        assert rows[0]["available"] is False

    async def test_buffer_empty_after_flush(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path, row_group_size=2)
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="A"))
        await store.process(_ArticleItem(url="http://b.com", title="B"))
        # buffer should have been flushed
        assert store._buffer == []
        await store.close()

    async def test_writer_closed_after_close(self, tmp_path: Path) -> None:
        path = tmp_path / "out.parquet"
        store = ParquetStore(path)
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="A"))
        await store.close()
        assert store._writer is None

    async def test_import_error_without_pyarrow(self) -> None:
        orig = sys.modules.get("pyarrow")
        sys.modules["pyarrow"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="chaser\\[parquet\\]"):
                ParquetStore("out.parquet")
        finally:
            if orig is None:
                del sys.modules["pyarrow"]
            else:
                sys.modules["pyarrow"] = orig
