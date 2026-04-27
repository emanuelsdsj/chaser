from __future__ import annotations

import asyncio
from pathlib import Path
from typing import IO

from chaser.item.base import Item
from chaser.pipeline.base import Stage


class JsonlStore(Stage):
    """Appends each item as one JSON line to a file.

    Opens in append mode so re-runs accumulate rather than clobber. An asyncio
    lock serializes concurrent writes — safe with any concurrency level.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._file: IO[str] | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        self._file = self._path.open("a", encoding="utf-8")

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    async def process(self, item: Item) -> Item:
        async with self._lock:
            if self._file is not None:
                self._file.write(item.model_dump_json() + "\n")
                self._file.flush()
        return item
