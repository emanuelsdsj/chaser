from __future__ import annotations

import asyncio
import math
from typing import Literal

import mmh3
from bitarray import bitarray

from chaser.net.request import Request


class BloomFilter:
    """Probabilistic set membership using MurmurHash3 + bitarray.

    Optimal bit-array size and hash count are derived from the declared
    capacity and the acceptable false-positive rate, so callers never
    need to tune those directly.
    """

    def __init__(self, capacity: int = 100_000, error_rate: float = 0.001) -> None:
        if not (0 < error_rate < 1):
            raise ValueError(f"error_rate must be between 0 and 1, got {error_rate}")
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")

        self.capacity = capacity
        self.error_rate = error_rate
        self._size = self._optimal_size(capacity, error_rate)
        self._hash_count = self._optimal_hash_count(self._size, capacity)
        self._bits = bitarray(self._size)
        self._bits.setall(0)
        self._count = 0

    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        """Bit-array length that achieves p false-positive rate for n items."""
        return max(1, int(-n * math.log(p) / (math.log(2) ** 2)))

    @staticmethod
    def _optimal_hash_count(m: int, n: int) -> int:
        """Number of hash functions that minimises false positives."""
        return max(1, int((m / n) * math.log(2)))

    def _positions(self, item: str) -> list[int]:
        return [mmh3.hash(item, seed=i, signed=False) % self._size for i in range(self._hash_count)]

    def add(self, item: str) -> None:
        for pos in self._positions(item):
            self._bits[pos] = 1
        self._count += 1

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return all(self._bits[pos] for pos in self._positions(item))

    def __len__(self) -> int:
        return self._count

    @property
    def estimated_fpr(self) -> float:
        """Current estimated false-positive rate based on items inserted so far."""
        k = self._hash_count
        m = self._size
        n = self._count
        if n == 0:
            return 0.0
        return (1 - math.exp(-k * n / m)) ** k


Strategy = Literal["bfs", "dfs", "score"]


class Frontier:
    """URL deduplication + request scheduling.

    Wraps a bloom filter for seen-URL tracking and an asyncio.PriorityQueue
    for ordered dispatch. Three scheduling strategies:

    - ``bfs``   — breadth-first; requests leave in insertion order (FIFO)
    - ``dfs``   — depth-first; most recently added request leaves first (LIFO)
    - ``score`` — user-controlled; higher ``request.priority`` leaves first
    """

    def __init__(
        self,
        strategy: Strategy = "bfs",
        bloom_capacity: int = 100_000,
        bloom_error_rate: float = 0.001,
    ) -> None:
        self._strategy: Strategy = strategy
        self._bloom = BloomFilter(capacity=bloom_capacity, error_rate=bloom_error_rate)
        # tuple: (sort_key, insertion_counter, request)
        # insertion_counter breaks ties and avoids comparing Request objects
        self._queue: asyncio.PriorityQueue[tuple[int, int, Request]] = asyncio.PriorityQueue()
        self._counter = 0

    def _sort_key(self, request: Request) -> int:
        """Lower value = pulled sooner (min-heap semantics)."""
        if self._strategy == "bfs":
            return self._counter
        if self._strategy == "dfs":
            return -self._counter
        # score: negate so higher priority wins
        return -request.priority

    def seen(self, url: str) -> bool:
        """Return True if this URL has already been scheduled."""
        return url in self._bloom

    async def push(self, request: Request) -> bool:
        """Enqueue a request.

        Returns False without enqueuing if the URL was seen before (dedup).
        Returns True when the request is accepted.
        """
        if request.url in self._bloom:
            return False
        self._bloom.add(request.url)
        await self._queue.put((self._sort_key(request), self._counter, request))
        self._counter += 1
        return True

    async def pop(self) -> Request:
        """Remove and return the next request. Blocks when the queue is empty."""
        _, _, request = await self._queue.get()
        return request

    def task_done(self) -> None:
        """Signal that a previously popped request has been processed."""
        self._queue.task_done()

    async def join(self) -> None:
        """Block until all popped requests have been marked task_done."""
        await self._queue.join()

    def empty(self) -> bool:
        return self._queue.empty()

    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def seen_count(self) -> int:
        """Number of distinct URLs that have passed through the frontier."""
        return len(self._bloom)
