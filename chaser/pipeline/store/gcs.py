from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from chaser.item.base import Item
from chaser.pipeline.base import Stage

logger = logging.getLogger(__name__)

_MISSING_GCS = "GCSStore requires google-cloud-storage — install with: pip install 'chaser[cloud]'"
_MISSING_PYARROW = (
    "GCSStore with .parquet blob requires pyarrow — install with: pip install 'chaser[parquet]'"
)


class GCSStore(Stage):
    """Writes crawled items to Google Cloud Storage as JSONL or Parquet.

    Items accumulate locally in a temp file and are uploaded in a single
    operation when close() is called. Format is inferred from the blob name
    extension: ``.parquet`` → Parquet (requires pyarrow), everything else →
    JSONL. The GCS client call runs in a thread executor so it does not block
    the event loop. Requires the ``cloud`` extra::

        pip install 'chaser[cloud]'

    Usage::

        GCSStore("my-bucket", "run/items.jsonl")
        GCSStore("my-bucket", "run/items.parquet")
        GCSStore("my-bucket", "run/items.jsonl", project="my-gcp-project")
    """

    def __init__(
        self,
        bucket: str,
        blob: str,
        *,
        project: str | None = None,
        credentials: Any = None,
    ) -> None:
        try:
            from google.cloud import storage  # noqa: F401
        except ImportError:
            raise ImportError(_MISSING_GCS) from None

        self._fmt = "parquet" if blob.endswith(".parquet") else "jsonl"
        if self._fmt == "parquet":
            try:
                import pyarrow  # noqa: F401
            except ImportError:
                raise ImportError(_MISSING_PYARROW) from None

        self._bucket_name = bucket
        self._blob_name = blob
        self._project = project
        self._credentials = credentials

        self._tmp_path: Path | None = None
        self._jsonl_handle: Any = None
        self._parquet_buffer: list[dict[str, Any]] = []
        self._count = 0
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        fd, path = tempfile.mkstemp(suffix=f".{self._fmt}")
        self._tmp_path = Path(path)
        if self._fmt == "jsonl":
            self._jsonl_handle = os.fdopen(fd, "w", encoding="utf-8")
        else:
            os.close(fd)
        self._count = 0
        self._parquet_buffer = []

    async def process(self, item: Item) -> Item:
        async with self._lock:
            self._count += 1
            if self._fmt == "jsonl":
                line = json.dumps(item.model_dump(), default=str)
                self._jsonl_handle.write(line + "\n")
            else:
                self._parquet_buffer.append(item.model_dump())
        return item

    async def close(self) -> None:
        async with self._lock:
            if self._fmt == "jsonl" and self._jsonl_handle is not None:
                self._jsonl_handle.flush()
                self._jsonl_handle.close()
                self._jsonl_handle = None
            elif self._fmt == "parquet":
                self._flush_parquet()

        tmp_path = self._tmp_path
        self._tmp_path = None

        if tmp_path is None or self._count == 0:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()
            return

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._upload_sync, str(tmp_path))
            logger.info(
                "GCSStore: %d items → gs://%s/%s",
                self._count,
                self._bucket_name,
                self._blob_name,
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _flush_parquet(self) -> None:
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        if not self._parquet_buffer or self._tmp_path is None:
            return
        table = pa.Table.from_pylist(self._parquet_buffer)
        pq.write_table(table, self._tmp_path)
        self._parquet_buffer.clear()

    def _upload_sync(self, tmp_path: str) -> None:
        from google.cloud import storage  # noqa: PLC0415

        client = storage.Client(
            project=self._project,
            credentials=self._credentials,
        )
        bucket = client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_name)
        content_type = "application/x-parquet" if self._fmt == "parquet" else "application/x-ndjson"
        blob.upload_from_filename(tmp_path, content_type=content_type)
