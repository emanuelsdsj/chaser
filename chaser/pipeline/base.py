from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import IO

from chaser.item.base import Item

logger = logging.getLogger(__name__)


class Stage:
    """Base class for pipeline stages.

    Override process() to transform or filter items. Return None to drop the
    item — it won't reach subsequent stages. open() and close() are called
    once at pipeline startup/teardown for resource management.
    """

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def process(self, item: Item) -> Item | None:
        return item


class Pipeline:
    """Async item processing chain.

    Runs registered stages in sequence. A stage returning None drops the item
    and skips the rest of the chain for that item. Stage exceptions are caught,
    logged at ERROR level, and treated the same as a drop.

    Pass ``dead_letter`` to capture items that cause stage failures — each
    failure is appended as a JSON line to that file with the item payload,
    the error, and the stage name. Useful for debugging and reprocessing.

    Usage::

        pipeline = Pipeline(
            [DuplicateFilter(key=lambda i: i.url), JsonlStore("out.jsonl")],
            dead_letter="failed.jsonl",
        )
        engine = Engine(pipeline=pipeline)
        await engine.run(MyTrapper())
    """

    def __init__(
        self,
        stages: list[Stage],
        *,
        dead_letter: str | Path | None = None,
    ) -> None:
        self._stages = stages
        self._dead_letter_path = Path(dead_letter) if dead_letter else None
        self._dead_letter_file: IO[str] | None = None
        self._dead_letter_lock = asyncio.Lock()

    async def open(self) -> None:
        for stage in self._stages:
            await stage.open()

    async def close(self) -> None:
        if self._dead_letter_file is not None:
            self._dead_letter_file.close()
            self._dead_letter_file = None
        for stage in reversed(self._stages):
            try:
                await stage.close()
            except Exception:
                logger.exception("Error closing pipeline stage %r", stage)

    async def process(self, item: Item) -> Item | None:
        current: Item | None = item
        for stage in self._stages:
            if current is None:
                return None
            try:
                current = await stage.process(current)
            except Exception as exc:
                logger.exception("Pipeline stage %r raised on %r — dropping", stage, item)
                await self._write_dead_letter(item, stage, exc)
                return None
        return current

    async def _write_dead_letter(self, item: Item, stage: Stage, exc: Exception) -> None:
        if self._dead_letter_path is None:
            return
        entry = {
            "timestamp": time.time(),
            "stage": type(stage).__name__,
            "error": repr(exc),
            "item": item.model_dump(),
        }
        async with self._dead_letter_lock:
            if self._dead_letter_file is None:
                self._dead_letter_file = self._dead_letter_path.open("a", encoding="utf-8")
            self._dead_letter_file.write(json.dumps(entry) + "\n")
            self._dead_letter_file.flush()

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        await self.open()
        try:
            yield
        finally:
            await self.close()
