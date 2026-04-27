from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from chaser.item.base import Item
from chaser.pipeline.store.csv import CsvStore
from chaser.pipeline.store.jsonl import JsonlStore


class _ArticleItem(Item):
    url: str
    title: str
    score: int = 0


class _ProductItem(Item):
    name: str
    price: float
    available: bool = True


# ---------------------------------------------------------------------------
# JsonlStore
# ---------------------------------------------------------------------------


class TestJsonlStore:
    async def test_writes_item_as_json_line(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        store = JsonlStore(path)
        await store.open()
        item = _ArticleItem(url="http://a.com", title="Hello", score=5)
        await store.process(item)
        await store.close()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data == {"url": "http://a.com", "title": "Hello", "score": 5}

    async def test_multiple_items_each_on_own_line(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        store = JsonlStore(path)
        await store.open()
        for i in range(4):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}"))
        await store.close()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 4

    async def test_appends_on_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        for _ in range(2):
            store = JsonlStore(path)
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="T"))
            await store.close()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2

    async def test_passes_item_through(self, tmp_path: Path) -> None:
        store = JsonlStore(tmp_path / "out.jsonl")
        await store.open()
        item = _ArticleItem(url="http://b.com", title="B")
        result = await store.process(item)
        await store.close()
        assert result is item

    async def test_no_write_when_not_opened(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        store = JsonlStore(path)
        # process without open — should silently skip, not crash
        await store.process(_ArticleItem(url="http://c.com", title="C"))
        assert not path.exists()


# ---------------------------------------------------------------------------
# CsvStore
# ---------------------------------------------------------------------------


class TestCsvStore:
    async def test_writes_header_and_row(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        store = CsvStore(path)
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="Hello", score=3))
        await store.close()

        with path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert rows[0] == {"url": "http://a.com", "title": "Hello", "score": "3"}

    async def test_multiple_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        store = CsvStore(path)
        await store.open()
        for i in range(3):
            await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
        await store.close()

        with path.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3

    async def test_passes_item_through(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        store = CsvStore(path)
        await store.open()
        item = _ArticleItem(url="http://a.com", title="A")
        result = await store.process(item)
        await store.close()
        assert result is item

    async def test_no_write_when_not_opened(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        store = CsvStore(path)
        await store.process(_ArticleItem(url="http://a.com", title="A"))
        assert not path.exists()

    async def test_different_item_types_write_own_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "out.csv"
        store = CsvStore(path)
        await store.open()
        # First item sets columns — this is the documented behaviour
        await store.process(_ArticleItem(url="http://a.com", title="A"))
        await store.close()

        with path.open() as f:
            reader = csv.DictReader(f)
            assert set(reader.fieldnames or []) == {"url", "title", "score"}


# ---------------------------------------------------------------------------
# DbStore
# ---------------------------------------------------------------------------


class TestDbStore:
    async def test_persists_item_to_sqlite(self) -> None:
        pytest.importorskip("sqlalchemy")
        pytest.importorskip("aiosqlite")

        from chaser.pipeline.store.db import DbStore

        store = DbStore("sqlite+aiosqlite:///:memory:")
        await store.open()
        item = _ArticleItem(url="http://a.com", title="Hello", score=7)
        result = await store.process(item)
        await store.close()

        assert result is item

    async def test_creates_table_from_item_fields(self) -> None:
        pytest.importorskip("sqlalchemy")
        pytest.importorskip("aiosqlite")

        from chaser.pipeline.store.db import DbStore

        store = DbStore("sqlite+aiosqlite:///:memory:")
        await store.open()
        await store.process(_ArticleItem(url="http://a.com", title="Test"))

        # Key is the class name, table name is lowercased
        assert "_ArticleItem" in store._tables
        await store.close()

    async def test_multiple_items_inserted(self) -> None:
        pytest.importorskip("sqlalchemy")
        pytest.importorskip("aiosqlite")

        from chaser.pipeline.store.db import DbStore

        store = DbStore("sqlite+aiosqlite:///:memory:")
        await store.open()
        for i in range(5):
            await store.process(_ArticleItem(url=f"http://a.com/{i}", title=f"T{i}"))
        await store.close()

    async def test_raises_on_missing_sqlalchemy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        # Temporarily hide sqlalchemy
        orig = sys.modules.get("sqlalchemy")
        sys.modules["sqlalchemy"] = None  # type: ignore[assignment]
        try:
            # Need to reimport to trigger the check

            with pytest.raises(ImportError, match="chaser\\[db\\]"):
                from chaser.pipeline.store.db import DbStore as _DbStore  # noqa: F401

                _DbStore("sqlite+aiosqlite:///:memory:")
        finally:
            if orig is None:
                del sys.modules["sqlalchemy"]
            else:
                sys.modules["sqlalchemy"] = orig
