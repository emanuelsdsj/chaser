from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from chaser.item.base import Item
from chaser.pipeline.store.gcs import GCSStore

pytest.importorskip("google.cloud.storage")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


class _ArticleItem(Item):
    url: str
    title: str
    score: int = 0


class _ProductItem(Item):
    name: str
    price: float


def _make_mock_gcs() -> tuple[Any, list[str]]:
    """Returns (patch context, list of paths passed to upload_from_filename)."""
    uploaded_contents: list[str] = []

    def fake_upload(path: str, content_type: str | None = None) -> None:
        with open(path) as fh:
            uploaded_contents.append(fh.read())

    mock_blob = MagicMock()
    mock_blob.upload_from_filename.side_effect = fake_upload

    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    ctx = patch("google.cloud.storage.Client", return_value=mock_client)
    return ctx, uploaded_contents


class TestGCSStoreJsonl:
    async def test_uploads_single_item(self) -> None:
        ctx, contents = _make_mock_gcs()
        with ctx:
            store = GCSStore("my-bucket", "run/items.jsonl")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="Hello"))
            await store.close()

        assert len(contents) == 1
        data = json.loads(contents[0].strip())
        assert data["url"] == "http://a.com"
        assert data["title"] == "Hello"

    async def test_uploads_multiple_items_as_jsonl(self) -> None:
        ctx, contents = _make_mock_gcs()
        with ctx:
            store = GCSStore("my-bucket", "run/items.jsonl")
            await store.open()
            for i in range(4):
                await store.process(_ArticleItem(url=f"http://x.com/{i}", title=f"T{i}", score=i))
            await store.close()

        lines = contents[0].strip().splitlines()
        assert len(lines) == 4
        assert json.loads(lines[2])["score"] == 2

    async def test_passes_item_through(self) -> None:
        ctx, _ = _make_mock_gcs()
        with ctx:
            store = GCSStore("my-bucket", "run/items.jsonl")
            await store.open()
            item = _ArticleItem(url="http://a.com", title="A")
            result = await store.process(item)
            await store.close()

        assert result is item

    async def test_skips_upload_when_no_items(self) -> None:
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            store = GCSStore("bucket", "out.jsonl")
            await store.open()
            await store.close()

        mock_blob.upload_from_filename.assert_not_called()

    async def test_bucket_and_blob_names_forwarded(self) -> None:
        mock_blob = MagicMock()
        mock_blob.upload_from_filename.side_effect = lambda p, content_type=None: None

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob

        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            store = GCSStore("the-bucket", "the/blob.jsonl", project="my-proj")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        mock_client.bucket.assert_called_once_with("the-bucket")
        mock_bucket.blob.assert_called_once_with("the/blob.jsonl")

    async def test_content_type_is_ndjson_for_jsonl(self) -> None:
        call_kwargs: dict[str, Any] = {}

        def capture_upload(path: str, content_type: str | None = None) -> None:
            call_kwargs["content_type"] = content_type

        mock_blob = MagicMock()
        mock_blob.upload_from_filename.side_effect = capture_upload
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            store = GCSStore("b", "out.jsonl")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        assert call_kwargs["content_type"] == "application/x-ndjson"

    async def test_temp_file_deleted_after_upload(self) -> None:
        ctx, _ = _make_mock_gcs()
        with ctx:
            store = GCSStore("bucket", "out.jsonl")
            await store.open()
            tmp_before = store._tmp_path
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        assert tmp_before is not None
        assert not tmp_before.exists()

    async def test_import_error_without_gcs(self) -> None:
        import google.cloud as _gc

        orig_mod = sys.modules.get("google.cloud.storage")
        orig_attr = getattr(_gc, "storage", None)
        sys.modules["google.cloud.storage"] = None  # type: ignore[assignment]
        if hasattr(_gc, "storage"):
            delattr(_gc, "storage")
        try:
            with pytest.raises(ImportError, match="google-cloud-storage"):
                GCSStore("bucket", "out.jsonl")
        finally:
            if orig_mod is None:
                sys.modules.pop("google.cloud.storage", None)
            else:
                sys.modules["google.cloud.storage"] = orig_mod
            if orig_attr is not None:
                _gc.storage = orig_attr


class TestGCSStoreParquet:
    async def test_uploads_parquet_file(self) -> None:
        uploaded_bytes: list[bytes] = []

        def fake_upload(path: str, content_type: str | None = None) -> None:
            with open(path, "rb") as fh:
                uploaded_bytes.append(fh.read())

        mock_blob = MagicMock()
        mock_blob.upload_from_filename.side_effect = fake_upload
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            store = GCSStore("bucket", "out.parquet")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A", score=7))
            await store.close()

        import io

        table = pq.read_table(io.BytesIO(uploaded_bytes[0]))
        rows = table.to_pylist()
        assert len(rows) == 1
        assert rows[0]["score"] == 7

    async def test_content_type_is_parquet(self) -> None:
        call_kwargs: dict[str, Any] = {}

        def capture_upload(path: str, content_type: str | None = None) -> None:
            call_kwargs["content_type"] = content_type

        mock_blob = MagicMock()
        mock_blob.upload_from_filename.side_effect = capture_upload
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with patch("google.cloud.storage.Client", return_value=mock_client):
            store = GCSStore("b", "out.parquet")
            await store.open()
            await store.process(_ArticleItem(url="http://a.com", title="A"))
            await store.close()

        assert call_kwargs["content_type"] == "application/x-parquet"

    async def test_import_error_parquet_without_pyarrow(self) -> None:
        orig = sys.modules.get("pyarrow")
        sys.modules["pyarrow"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="pyarrow"):
                GCSStore("bucket", "out.parquet")
        finally:
            if orig is None:
                del sys.modules["pyarrow"]
            else:
                sys.modules["pyarrow"] = orig
