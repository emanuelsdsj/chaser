from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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

    Usage::

        pipeline = Pipeline([DuplicateFilter(), JsonlStore("out.jsonl")])
        engine = Engine(pipeline=pipeline)
        await engine.run(MyTrapper())

    Or manually manage the lifecycle::

        async with pipeline.run():
            await engine.run(MyTrapper(), pipeline=pipeline)
    """

    def __init__(self, stages: list[Stage]) -> None:
        self._stages = stages

    async def open(self) -> None:
        for stage in self._stages:
            await stage.open()

    async def close(self) -> None:
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
            except Exception:
                logger.exception("Pipeline stage %r raised on %r — dropping", stage, item)
                return None
        return current

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        await self.open()
        try:
            yield
        finally:
            await self.close()
