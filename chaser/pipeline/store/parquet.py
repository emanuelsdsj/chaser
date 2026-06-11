from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chaser.item.base import Item
from chaser.pipeline.base import Stage

if TYPE_CHECKING:
    import pyarrow as pa
    import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_MISSING = "ParquetStore requires pyarrow — install with: pip install 'chaser[parquet]'"


class ParquetStore(Stage):
    """Writes items to a Parquet file using pyarrow.

    Rows are buffered and flushed as row groups — one group per
    ``row_group_size`` items, plus a final flush on close(). Schema is
    inferred from the first flush and fixed for the run, so items must have
    consistent field types (same Pydantic model). Requires the ``parquet``
    extra::

        pip install 'chaser[parquet]'

    Usage::

        ParquetStore("output.parquet")
        ParquetStore("output.parquet", row_group_size=5000)
    """

    def __init__(self, path: str | Path, *, row_group_size: int = 1000) -> None:
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise ImportError(_MISSING) from None

        self._path = Path(path)
        self._row_group_size = row_group_size
        self._buffer: list[dict[str, Any]] = []
        self._writer: pq.ParquetWriter | None = None
        self._schema: pa.Schema | None = None
        self._lock = asyncio.Lock()
        self._is_open = False

    async def open(self) -> None:
        self._is_open = True

    async def close(self) -> None:
        async with self._lock:
            self._is_open = False
            self._flush_sync()
            if self._writer is not None:
                self._writer.close()
                self._writer = None

    async def process(self, item: Item) -> Item:
        async with self._lock:
            if not self._is_open:
                return item
            self._buffer.append(item.model_dump())
            if len(self._buffer) >= self._row_group_size:
                self._flush_sync()
        return item

    def _flush_sync(self) -> None:
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        if not self._buffer:
            return

        table = pa.Table.from_pylist(self._buffer)
        if self._writer is None:
            self._schema = table.schema
            self._writer = pq.ParquetWriter(self._path, self._schema)
        else:
            table = table.cast(self._schema)
        self._writer.write_table(table)
        self._buffer.clear()
