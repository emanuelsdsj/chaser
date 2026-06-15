from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chaser.item.base import Item
from chaser.pipeline.store.s3 import S3Store

aioboto3 = pytest.importorskip("aioboto3")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


class _ArticleItem(Item):
    url: str
    title: str
    score: int = 0


class _ProductItem(Item):
    name: str
    price: float


def _make_mock_s3() -> tuple[Any, list[bytes]]:
    """Returns (mock_s3_client, captured_bodies) — bodies appended on each put_object call."""
    captured: list[bytes] = []

    async def fake_put_object(**kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs["Body"])
        return {}

    mock_s3 = AsyncMock()
    mock_s3.put_object = fake_put_object

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_s3)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return ctx, captured


def _patch_session(ctx: Any) -> Any:
    mock_session = MagicMock()
    mock_session.client.return_value = ctx
    return patch("aioboto3.Session", return_value=mock_session)


class TestS3StoreJsonl:
    async def test_uploads_single_item(self) -> None:
        ctx, captured = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.jsonl")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        assert len(captured) == 1
        data = json.loads(captured[0].decode())
        assert data["url"] == "http://a.com"
        assert data["title"] == "A"
        assert data["score"] == 0

    async def test_uploads_multiple_items_as_jsonl(self) -> None:
        ctx, captured = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.jsonl")
            await store.open()
            for i in range(3):
                await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
            await store.close()

        lines = captured[0].decode().strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[1])["score"] == 1

    async def test_passes_item_through(self) -> None:
        ctx, _ = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.jsonl")
            await store.open()
            item = _ArticleItem(url="http://a.com", title="A")
            result = await store.process(item)
            await store.close()

        assert result is item

    async def test_skips_upload_when_no_items(self) -> None:
        ctx, captured = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.jsonl")
            await store.open()
            await store.close()

        assert len(captured) == 0

    async def test_client_kwargs_forwarded(self) -> None:
        ctx, _ = _make_mock_s3()
        mock_session = MagicMock()
        mock_session.client.return_value = ctx

        with patch("aioboto3.Session", return_value=mock_session):
            store = S3Store(
                "bucket",
                "out.jsonl",
                endpoint_url="http://minio:9000",
                region_name="us-east-1",
                aws_access_key_id="key",
                aws_secret_access_key="secret",
            )
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        mock_session.client.assert_called_once_with(
            "s3",
            endpoint_url="http://minio:9000",
            region_name="us-east-1",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
        )

    async def test_temp_file_deleted_after_upload(self, tmp_path: Any) -> None:
        seen_paths: list[str] = []

        async def fake_put_object(**kwargs: Any) -> dict[str, Any]:
            seen_paths.append(str(kwargs["Body"]))
            return {}

        ctx, _ = _make_mock_s3()
        ctx.__aenter__.return_value.put_object = fake_put_object

        with _patch_session(ctx):
            store = S3Store("bucket", "out.jsonl")
            await store.open()
            tmp_before = store._tmp_path
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        assert tmp_before is not None
        assert not tmp_before.exists()

    async def test_import_error_without_aioboto3(self) -> None:
        orig = sys.modules.get("aioboto3")
        sys.modules["aioboto3"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="aioboto3"):
                S3Store("bucket", "out.jsonl")
        finally:
            if orig is None:
                del sys.modules["aioboto3"]
            else:
                sys.modules["aioboto3"] = orig


class TestS3StoreParquet:
    async def test_uploads_parquet_file(self) -> None:
        ctx, captured = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.parquet")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A", score=42))
            await store.close()

        assert len(captured) == 1
        import io

        table = pq.read_table(io.BytesIO(captured[0]))
        rows = table.to_pylist()
        assert len(rows) == 1
        assert rows[0]["url"] == "http://a.com"
        assert rows[0]["score"] == 42

    async def test_parquet_multiple_items(self) -> None:
        ctx, captured = _make_mock_s3()
        with _patch_session(ctx):
            store = S3Store("bucket", "out.parquet")
            await store.open()
            for i in range(5):
                await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
            await store.close()

        import io

        table = pq.read_table(io.BytesIO(captured[0]))
        assert table.num_rows == 5

    async def test_parquet_format_detected_from_extension(self) -> None:
        ctx, _ = _make_mock_s3()
        with _patch_session(ctx):
            s = S3Store("b", "data.parquet")
            assert s._fmt == "parquet"

            s2 = S3Store("b", "data.jsonl")
            assert s2._fmt == "jsonl"

            s3 = S3Store("b", "data.csv")
            assert s3._fmt == "jsonl"

    async def test_import_error_parquet_without_pyarrow(self) -> None:
        orig = sys.modules.get("pyarrow")
        sys.modules["pyarrow"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="pyarrow"):
                S3Store("bucket", "out.parquet")
        finally:
            if orig is None:
                del sys.modules["pyarrow"]
            else:
                sys.modules["pyarrow"] = orig
