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

_MISSING_AIOBOTO3 = "S3Store requires aioboto3 — install with: pip install 'chaser[cloud]'"
_MISSING_PYARROW = (
    "S3Store with .parquet key requires pyarrow — install with: pip install 'chaser[parquet]'"
)


class S3Store(Stage):
    """Writes crawled items to Amazon S3 (or any S3-compatible endpoint) as JSONL or Parquet.

    Items accumulate locally in a temp file and are uploaded in a single PUT
    when close() is called. Format is inferred from the key extension:
    ``.parquet`` → Parquet (requires pyarrow), everything else → JSONL.
    Requires the ``cloud`` extra::

        pip install 'chaser[cloud]'

    Usage::

        S3Store("my-bucket", "run/items.jsonl")
        S3Store("my-bucket", "run/items.parquet")
        S3Store("my-bucket", "run/items.jsonl", endpoint_url="http://minio:9000")
    """

    def __init__(
        self,
        bucket: str,
        key: str,
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        try:
            import aioboto3  # noqa: F401
        except ImportError:
            raise ImportError(_MISSING_AIOBOTO3) from None

        self._fmt = "parquet" if key.endswith(".parquet") else "jsonl"
        if self._fmt == "parquet":
            try:
                import pyarrow  # noqa: F401
            except ImportError:
                raise ImportError(_MISSING_PYARROW) from None

        self._bucket = bucket
        self._key = key
        self._client_kwargs: dict[str, Any] = {}
        if endpoint_url:
            self._client_kwargs["endpoint_url"] = endpoint_url
        if region_name:
            self._client_kwargs["region_name"] = region_name
        if aws_access_key_id:
            self._client_kwargs["aws_access_key_id"] = aws_access_key_id
        if aws_secret_access_key:
            self._client_kwargs["aws_secret_access_key"] = aws_secret_access_key

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
            await self._upload(tmp_path)
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

    async def _upload(self, tmp_path: Path) -> None:
        import aioboto3  # noqa: PLC0415

        session = aioboto3.Session()
        async with session.client("s3", **self._client_kwargs) as s3:
            with open(tmp_path, "rb") as fh:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=self._key,
                    Body=fh.read(),
                )
        logger.info(
            "S3Store: %d items → s3://%s/%s",
            self._count,
            self._bucket,
            self._key,
        )
