from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chaser.engine import trap
from chaser.engine.stats import CrawlStats
from chaser.frontier.queue import Frontier
from chaser.hooks.base import RequestAborted
from chaser.item.base import Item
from chaser.net.client import CircuitOpenError, FetchError, NetClient, TimeoutFetchError
from chaser.net.request import Request
from chaser.trapper.base import Trapper

if TYPE_CHECKING:
    from chaser.browser.client import BrowserClient
    from chaser.frontier.sqlite import SqliteFrontier
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

    Set ``browser=True`` to enable Playwright for requests that have
    ``use_browser=True``. Requires the ``chaser[browser]`` extra.

    Usage::

        engine = Engine(concurrency=16)
        items = await engine.run(MyTrapper())
        print(engine.stats)
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
        browser: bool = False,
        cache_dir: str | Path | None = None,
        on_stats: Callable[[CrawlStats], Any] | None = None,
        stats_interval: float = 60.0,
        frontier_db: str | Path | None = None,
    ) -> None:
        self._concurrency = concurrency
        self._strategy = strategy
        self._net_kwargs: dict[str, Any] = {
            "http2": http2,
            "timeout": timeout,
            "max_connections": max_connections,
            "proxy": proxy,
            "hooks": hooks or [],
        }
        if cache_dir is not None:
            from chaser.net.cache import HttpCache

            self._net_kwargs["cache"] = HttpCache(cache_dir)
        self._frontier_db: Path | None = Path(frontier_db) if frontier_db is not None else None
        self._frontier: Frontier | SqliteFrontier = Frontier(strategy=strategy)  # type: ignore[arg-type]
        self._items: list[Item] = []
        self._retry = retry
        self._pipeline = pipeline
        self._use_browser = browser
        self._on_stats = on_stats
        self._stats_interval = stats_interval
        self.stats = CrawlStats()

    async def run(self, trappers: Sequence[Trapper] | Trapper) -> list[Item]:
        """Run the crawl and return collected items.

        Blocks until the frontier is drained. Access ``engine.stats`` after
        this returns for request/item/timing counters.
        """
        if isinstance(trappers, Trapper):
            trappers = [trappers]

        self.stats = CrawlStats()
        self._items = []

        if self._frontier_db is not None:
            from chaser.frontier.sqlite import SqliteFrontier

            sf = SqliteFrontier(self._frontier_db, strategy=self._strategy)
            sf.open()
            self._frontier = sf
        else:
            self._frontier = Frontier(strategy=self._strategy)  # type: ignore[arg-type]

        trapper_map: dict[str, Trapper] = {t.name: t for t in trappers}

        pipeline_ctx = self._pipeline.run() if self._pipeline else nullcontext()
        browser_ctx: Any = self._make_browser_ctx() if self._use_browser else nullcontext()

        for trapper in trappers:
            await trapper.open()

        stats_task: asyncio.Task[None] | None = None
        try:
            async with (
                browser_ctx as browser_client,
                pipeline_ctx,
                NetClient(**self._net_kwargs) as net,
            ):
                for trapper in trappers:
                    for req in trapper.start_requests():
                        req.meta.setdefault("trapper", trapper.name)
                        await self._frontier.push(req)

                if self._frontier.empty():
                    logger.warning("No start requests found — nothing to crawl")
                    self.stats._mark_finished()
                    return self._items

                if self._on_stats is not None:
                    stats_task = asyncio.create_task(self._stats_reporter())

                workers = [
                    asyncio.create_task(self._worker(net, browser_client, trapper_map))
                    for _ in range(self._concurrency)
                ]

                await self._frontier.join()

                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
        finally:
            if stats_task is not None:
                stats_task.cancel()
                await asyncio.gather(stats_task, return_exceptions=True)

            for trapper in reversed(list(trappers)):
                try:
                    await trapper.close()
                except Exception:
                    logger.exception("Error closing trapper %r", trapper.name)

            if self._frontier_db is not None:
                from chaser.frontier.sqlite import SqliteFrontier

                if isinstance(self._frontier, SqliteFrontier):
                    self._frontier.close()

        self.stats._mark_finished()
        return self._items

    def _make_browser_ctx(self) -> BrowserClient:
        from chaser.browser.client import BrowserClient

        return BrowserClient()

    async def _stats_reporter(self) -> None:
        assert self._on_stats is not None
        while True:
            result = self._on_stats(self.stats.snapshot())
            if asyncio.iscoroutine(result):
                await result
            await asyncio.sleep(self._stats_interval)

    async def _worker(
        self,
        net: NetClient,
        browser_client: BrowserClient | None,
        trapper_map: dict[str, Trapper],
    ) -> None:
        while True:
            request = await self._frontier.pop()
            try:
                await self._dispatch(net, browser_client, trapper_map, request)
            finally:
                self._frontier.task_done()

    async def _dispatch(
        self,
        net: NetClient,
        browser_client: BrowserClient | None,
        trapper_map: dict[str, Trapper],
        request: Request,
    ) -> None:
        self.stats.requests_sent += 1

        trapper_name = request.meta.get("trapper", "")
        trapper = trapper_map.get(trapper_name)
        if trapper is not None and trapper.custom_settings:
            delay = trapper.custom_settings.get("download_delay")
            if delay:
                await asyncio.sleep(float(delay))
            user_agent = trapper.custom_settings.get("user_agent")
            if user_agent and "user-agent" not in {k.lower() for k in request.headers}:
                from chaser.net.headers import Headers

                request = request.copy(
                    headers=Headers({**dict(request.headers), "user-agent": user_agent})
                )

        if request.use_browser:
            if browser_client is None:
                logger.warning(
                    "use_browser=True on %s but Engine(browser=False) — fetching with net client",
                    request.url,
                )
                response = await self._fetch_with_retry(net, request)
            else:
                try:
                    response = await browser_client.fetch(request)
                    self.stats.requests_ok += 1
                    self.stats.bytes_downloaded += len(response.body)
                except Exception as exc:
                    logger.warning("Browser fetch failed — %s: %s", request.url, exc)
                    self.stats.requests_failed += 1
                    return
        else:
            response = await self._fetch_with_retry(net, request)

        if response is None:
            return

        if response.status >= 400:
            self.stats._record_status_error(response.status)

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
                self.stats.items_scraped += 1
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

    async def _fetch_with_retry(self, net: NetClient, request: Request) -> Any:
        attempt = 0
        while True:
            try:
                response = await net.fetch(request)
                if response.from_cache:
                    self.stats.cache_hits += 1
                else:
                    self.stats.requests_ok += 1
                    self.stats.bytes_downloaded += len(response.body)
                return response
            except CircuitOpenError as exc:
                logger.debug("Circuit open — skipping %s (%s)", request.url, exc)
                self.stats.requests_failed += 1
                return None
            except RequestAborted as exc:
                logger.debug("Request aborted by hook — %s: %s", request.url, exc)
                self.stats.requests_failed += 1
                return None
            except TimeoutFetchError as exc:
                if self._retry and self._retry.should_retry(attempt, exc):
                    await self._retry.wait(attempt)
                    attempt += 1
                else:
                    logger.warning("Fetch timed out — %s: %s", request.url, exc)
                    self.stats.timeouts += 1
                    self.stats.requests_failed += 1
                    return None
            except FetchError as exc:
                if self._retry and self._retry.should_retry(attempt, exc):
                    await self._retry.wait(attempt)
                    attempt += 1
                else:
                    logger.warning("Fetch failed — %s: %s", request.url, exc)
                    self.stats.requests_failed += 1
                    return None
