from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import IO

from chaser.item.base import Item
from chaser.pipeline.base import Stage


class CsvStore(Stage):
    """Writes items to a CSV file.

    Column names are derived from the first item's fields — header is written
    automatically. Extra keys are ignored; missing keys default to an empty
    string. An asyncio lock serializes concurrent writes.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._file: IO[str] | None = None
        self._writer: csv.DictWriter[str] | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        self._file = self._path.open("w", newline="", encoding="utf-8")

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    async def process(self, item: Item) -> Item:
        async with self._lock:
            if self._file is None:
                return item
            data = item.model_dump()
            if self._writer is None:
                self._writer = csv.DictWriter(
                    self._file,
                    fieldnames=list(data.keys()),
                    extrasaction="ignore",
                    restval="",
                )
                self._writer.writeheader()
            self._writer.writerow(data)
            self._file.flush()
        return item
