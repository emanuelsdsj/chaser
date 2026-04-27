from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any

from chaser.engine import trap
from chaser.frontier.queue import Frontier
from chaser.hooks.base import RequestAborted
from chaser.item.base import Item
from chaser.net.client import CircuitOpenError, FetchError, NetClient
from chaser.net.request import Request
from chaser.trapper.base import Trapper

if TYPE_CHECKING:
    from chaser.hooks.base import FetchHook
    from chaser.hooks.retry import RetryPolicy
    from chaser.pipeline.base import Pipeline

logger = logging.getLogger(__name__)


class Engine:
    """Async crawl coordinator.

    Wires together Frontier (dedup + scheduling), NetClient (HTTP fetching),
    and the Trap Layer (isolated parse execution). Workers pull requests from
    the Frontier, fetch them, and pipe results back — new Requests re-enter
    the Frontier, Items accumulate in memory.

    Usage::

        engine = Engine(concurrency=16)
        items = await engine.run(MyTrpper())
    """

    def __init__(
        self,
        *,
        concurrency: int = 16,
        strategy: str = "bfs",
        http2: bool = True,
        timeout: float = 30.0,
        max_connections: int = 100,
        proxy: str | None = None,
        hooks: list[FetchHook] | None = None,
        retry: RetryPolicy | None = None,
        pipeline: Pipeline | None = None,
    ) -> None:
        self._concurrency = concurrency
        self._net_kwargs: dict[str, Any] = {
            "http2": http2,
            "timeout": timeout,
            "max_connections": max_connections,
            "proxy": proxy,
            "hooks": hooks or [],
        }
        self._frontier = Frontier(strategy=strategy)  # type: ignore[arg-type]
        self._items: list[Item] = []
        self._retry = retry
        self._pipeline = pipeline

    async def run(self, trappers: Sequence[Trapper] | Trapper) -> list[Item]:
        """Run the crawl and return collected items.

        Blocks until the frontier is drained — all reachable URLs have been
        fetched and parsed. Returns the accumulated ``Item`` list.
        """
        if isinstance(trappers, Trapper):
            trappers = [trappers]

        trapper_map: dict[str, Trapper] = {t.name: t for t in trappers}

        pipeline_ctx = self._pipeline.run() if self._pipeline else nullcontext()
        async with pipeline_ctx, NetClient(**self._net_kwargs) as net:
            for trapper in trappers:
                for req in trapper.start_requests():
                    req.meta.setdefault("trapper", trapper.name)
                    await self._frontier.push(req)

            if self._frontier.empty():
                logger.warning("No start requests found — nothing to crawl")
                return self._items

            workers = [
                asyncio.create_task(self._worker(net, trapper_map))
                for _ in range(self._concurrency)
            ]

            await self._frontier.join()

            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        return self._items

    async def _worker(self, net: NetClient, trapper_map: dict[str, Trapper]) -> None:
        while True:
            request = await self._frontier.pop()
            try:
                await self._dispatch(net, trapper_map, request)
            finally:
                self._frontier.task_done()

    async def _dispatch(
        self,
        net: NetClient,
        trapper_map: dict[str, Trapper],
        request: Request,
    ) -> None:
        attempt = 0
        while True:
            try:
                response = await net.fetch(request)
                break
            except CircuitOpenError as exc:
                logger.debug("Circuit open — skipping %s (%s)", request.url, exc)
                return
            except RequestAborted as exc:
                logger.debug("Request aborted by hook — %s: %s", request.url, exc)
                return
            except FetchError as exc:
                if self._retry and self._retry.should_retry(attempt, exc):
                    await self._retry.wait(attempt)
                    attempt += 1
                else:
                    logger.warning("Fetch failed — %s: %s", request.url, exc)
                    return

        trapper_name = request.meta.get("trapper", "")
        trapper = trapper_map.get(trapper_name)
        if trapper is None:
            logger.warning(
                "No trapper %r registered for %s — dropping response",
                trapper_name,
                request.url,
            )
            return

        async for result in trap.execute(trapper, response, request.callback):
            if isinstance(result, Request):
                result.meta.setdefault("trapper", trapper_name)
                await self._frontier.push(result)
            elif isinstance(result, Item):
                if self._pipeline is not None:
                    await self._pipeline.process(result)
                else:
                    self._items.append(result)
            else:
                logger.warning(
                    "Trapper %r yielded unexpected type %s — ignoring",
                    trapper_name,
                    type(result).__name__,
                )
