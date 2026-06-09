from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from chaser.frontier.queue import canonicalize
from chaser.net.request import Request

logger = logging.getLogger(__name__)


class RedisFrontier:
    """Distributed crawl frontier backed by Redis.

    Deduplication and scheduling live in Redis so multiple processes
    (or machines) can share a single frontier.  Each process connects
    to the same server and coordinates atomically via HSETNX + ZADD.

    Scheduling strategies:
    - ``bfs``   — breadth-first (insertion order, FIFO)
    - ``dfs``   — depth-first (reverse insertion order, LIFO)
    - ``score`` — higher ``request.priority`` leaves first

    Crash recovery: on ``open()``, any request that was in-flight when
    the previous process died is moved back to pending automatically.
    Pass ``clear=True`` to wipe all keys and start fresh.

    The public interface mirrors ``Frontier`` and ``SqliteFrontier`` so
    it drops into the Engine without changes to call sites.

    Note: ``request.meta`` values must be JSON-serialisable.
    Requires: ``pip install 'chaser[redis]'``
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "chaser",
        strategy: str = "bfs",
        sort_params: bool = False,
        clear: bool = False,
    ) -> None:
        self._redis_url = redis_url
        self._prefix = prefix
        self._strategy = strategy
        self._sort_params = sort_params
        self._clear = clear

        self._redis: Any = None

        # task_id → stack of Redis slot ids.  A stack handles the (rare) case
        # where the same coroutine calls pop() multiple times before task_done().
        self._inflight: dict[int, list[str]] = {}

        # Local join() tracking — counts this process's unfinished pops.
        # join() waits for this to hit 0, then checks global Redis state.
        self._local_unfinished: int = 0
        self._local_done = asyncio.Event()
        self._local_done.set()

        # Approximate hints updated on push/pop (may lag other processes)
        self._queue_size_hint: int = 0
        self._seen_count_local: int = 0

    # ------------------------------------------------------------------ #
    # Redis key helpers                                                    #
    # ------------------------------------------------------------------ #

    @property
    def _key_seen(self) -> str:
        # HASH: canonical_url → "1"; HSETNX gives atomic check-and-set
        return f"{self._prefix}:seen"

    @property
    def _key_queue(self) -> str:
        return f"{self._prefix}:queue"

    @property
    def _key_counter(self) -> str:
        return f"{self._prefix}:counter"

    @property
    def _key_inflight(self) -> str:
        return f"{self._prefix}:inflight"

    # ------------------------------------------------------------------ #
    # lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def open(self) -> None:
        """Connect to Redis and restore state from a previous run.

        Recovers in-flight requests that were interrupted by a crash.
        Must be called before any push/pop operations.
        """
        try:
            import redis.asyncio as aioredis
        except ImportError as exc:
            raise ImportError(
                "chaser[redis] is required for RedisFrontier — "
                "install it with: pip install 'chaser[redis]'"
            ) from exc

        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)

        if self._clear:
            await self._redis.delete(
                self._key_seen,
                self._key_queue,
                self._key_counter,
                self._key_inflight,
            )
            logger.info("RedisFrontier(%r): all keys cleared", self._prefix)
            return

        # Crash recovery: put any in-flight items back into the sorted queue
        inflight = await self._redis.hgetall(self._key_inflight)
        if inflight:
            pipe = self._redis.pipeline()
            for member_json in inflight.values():
                data = json.loads(member_json)
                score = self._score(data["counter"], data.get("priority", 0))
                pipe.zadd(self._key_queue, {member_json: score})
            pipe.delete(self._key_inflight)
            await pipe.execute()
            logger.info(
                "RedisFrontier(%r): crash recovery — %d requests moved back to pending",
                self._prefix,
                len(inflight),
            )

        self._seen_count_local = await self._redis.hlen(self._key_seen)
        self._queue_size_hint = await self._redis.zcard(self._key_queue)

        if self._queue_size_hint > 0:
            logger.info(
                "RedisFrontier(%r): resuming — %d pending, %d seen URLs",
                self._prefix,
                self._queue_size_hint,
                self._seen_count_local,
            )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ------------------------------------------------------------------ #
    # public interface                                                     #
    # ------------------------------------------------------------------ #

    def seen(self, url: str) -> bool:
        """Not supported synchronously — use ``seen_async()`` instead."""
        raise RuntimeError(
            "RedisFrontier.seen() cannot run synchronously. "
            "Use `await frontier.seen_async(url)` instead."
        )

    async def seen_async(self, url: str) -> bool:
        """Return True if this URL has already been scheduled."""
        assert self._redis is not None, "call open() first"
        return bool(await self._redis.hexists(self._key_seen, self._canonical(url)))

    async def push(self, request: Request) -> bool:
        """Enqueue a request.

        Uses HSETNX for an atomic check-and-mark of the seen set.
        Returns False if the URL was already seen.  Multiple processes
        calling push() concurrently for the same URL are safe — only
        one will get the HSETNX slot and add the request to the queue.
        """
        assert self._redis is not None, "call open() first"
        key = self._canonical(request.url)
        counter = await self._redis.incr(self._key_counter)
        score = self._score(counter, request.priority)
        member = json.dumps(
            {"counter": counter, "priority": request.priority, "request": request.to_dict()}
        )

        # HSETNX is atomic: returns 1 if the field was set, 0 if it already existed
        added = await self._redis.hsetnx(self._key_seen, key, "1")
        if not added:
            return False

        await self._redis.zadd(self._key_queue, {member: score})
        self._seen_count_local += 1
        self._queue_size_hint += 1
        return True

    async def pop(self) -> Request:
        """Remove and return the next request.  Blocks until one is available."""
        assert self._redis is not None, "call open() first"
        while True:
            result = await self._redis.bzpopmin(self._key_queue, timeout=1)
            if result is not None:
                break

        _key, member_json, _score = result
        data = json.loads(member_json)
        request = Request.from_dict(data["request"])

        slot_id = uuid.uuid4().hex
        task_id = id(asyncio.current_task())
        self._inflight.setdefault(task_id, []).append(slot_id)
        await self._redis.hset(self._key_inflight, slot_id, member_json)

        self._queue_size_hint = max(0, self._queue_size_hint - 1)
        self._local_unfinished += 1
        self._local_done.clear()

        return request

    def task_done(self) -> None:
        """Signal that a previously popped request has been processed."""
        assert self._redis is not None, "call open() first"
        task_id = id(asyncio.current_task())
        slots = self._inflight.get(task_id)
        if slots:
            slot_id = slots.pop()
            if not slots:
                del self._inflight[task_id]
            asyncio.get_running_loop().create_task(self._redis.hdel(self._key_inflight, slot_id))

        self._local_unfinished = max(0, self._local_unfinished - 1)
        if self._local_unfinished == 0:
            self._local_done.set()

    async def join(self) -> None:
        """Block until the queue is empty and no requests are in flight.

        In multi-process mode this checks the global Redis state, so
        the call only returns once ALL processes have finished.
        """
        assert self._redis is not None, "call open() first"
        while True:
            # Wait for this process's workers to finish their current batch
            await self._local_done.wait()

            # Check whether any work remains globally
            queue_size = await self._redis.zcard(self._key_queue)
            inflight_count = await self._redis.hlen(self._key_inflight)
            if queue_size == 0 and inflight_count == 0:
                return

            await asyncio.sleep(0.05)

    def empty(self) -> bool:
        """Approximate check — True if this process has seen no pending items."""
        return self._queue_size_hint <= 0

    def qsize(self) -> int:
        """Approximate queue size from this process's local view."""
        return max(0, self._queue_size_hint)

    @property
    def seen_count(self) -> int:
        """Approximate count of distinct URLs seen (may lag other processes)."""
        return self._seen_count_local

    # ------------------------------------------------------------------ #
    # private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _canonical(self, url: str) -> str:
        return canonicalize(url, sort_params=self._sort_params)

    def _score(self, counter: int, priority: int) -> float:
        """Lower score = popped sooner (Redis ZPOPMIN semantics)."""
        if self._strategy == "bfs":
            return float(counter)
        if self._strategy == "dfs":
            return float(-counter)
        # score strategy: higher priority → lower score → popped first
        return float(-priority)
