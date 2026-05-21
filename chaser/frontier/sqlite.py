from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from pathlib import Path

from chaser.frontier.queue import canonicalize
from chaser.net.request import Request

logger = logging.getLogger(__name__)

_SCHEMA = """\
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS seen_urls (
    url TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS queue (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    url      TEXT    NOT NULL,
    data     TEXT    NOT NULL,
    state    TEXT    NOT NULL DEFAULT 'pending',
    sort_key INTEGER NOT NULL,
    counter  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_state ON queue (state);
"""


class SqliteFrontier:
    """Persistent crawl frontier backed by SQLite.

    Stores seen URLs and pending requests on disk so a crawl can resume
    after a crash or a deliberate stop.  On the next ``open()`` call, any
    request that was in-flight when the process died is moved back to
    ``pending`` — nothing is silently dropped.

    The public interface mirrors ``Frontier`` so it slots straight into
    the Engine without any other changes.

    Note: ``request.meta`` values must be JSON-serialisable.
    """

    def __init__(
        self,
        db_path: str | Path,
        strategy: str = "bfs",
        sort_params: bool = False,
    ) -> None:
        self._db_path = Path(db_path)
        self._strategy = strategy
        self._sort_params = sort_params
        # (sort_key, counter, row_id, request)
        self._queue: asyncio.PriorityQueue[tuple[int, int, int, Request]] = asyncio.PriorityQueue()
        self._counter = 0
        self._seen_count = 0
        # asyncio task id → sqlite row id, tracks what each worker has in flight
        self._in_flight: dict[int, int] = {}
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ #
    # lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open (or create) the database and restore persisted state.

        Must be called before any push/pop operations.
        """
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

        # Crash recovery: anything in_flight when we died hasn't been processed
        self._conn.execute("UPDATE queue SET state='pending' WHERE state='in_flight'")
        self._conn.commit()

        row = self._conn.execute("SELECT COUNT(*) FROM seen_urls").fetchone()
        self._seen_count = row[0]

        rows = self._conn.execute(
            "SELECT id, data, sort_key, counter FROM queue"
            " WHERE state='pending' ORDER BY sort_key, counter"
        ).fetchall()

        for row_id, data_json, sort_key, counter in rows:
            req = Request.from_dict(json.loads(data_json))
            self._queue.put_nowait((sort_key, counter, row_id, req))
            if counter >= self._counter:
                self._counter = counter + 1

        if rows:
            logger.info(
                "Resuming crawl: %d pending requests, %d seen URLs from %s",
                len(rows),
                self._seen_count,
                self._db_path,
            )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------ #
    # public interface (matches Frontier)                                  #
    # ------------------------------------------------------------------ #

    def seen(self, url: str) -> bool:
        assert self._conn is not None, "call open() first"
        key = self._canonical(url)
        return (
            self._conn.execute("SELECT 1 FROM seen_urls WHERE url=?", (key,)).fetchone() is not None
        )

    async def push(self, request: Request) -> bool:
        """Enqueue a request.

        Returns False without enqueuing if the URL was seen before.
        The seen-check and the DB write happen without any ``await`` in
        between, so concurrent workers can't race past the dedup guard.
        """
        assert self._conn is not None, "call open() first"
        key = self._canonical(request.url)

        if self._conn.execute("SELECT 1 FROM seen_urls WHERE url=?", (key,)).fetchone() is not None:
            return False

        sort_key = self._sort_key(request)
        counter = self._counter
        self._counter += 1
        self._seen_count += 1

        data_json = json.dumps(request.to_dict())
        with self._conn:
            self._conn.execute("INSERT INTO seen_urls (url) VALUES (?)", (key,))
            cursor = self._conn.execute(
                "INSERT INTO queue (url, data, state, sort_key, counter)"
                " VALUES (?, ?, 'pending', ?, ?)",
                (request.url, data_json, sort_key, counter),
            )
            row_id: int = cursor.lastrowid  # type: ignore[assignment]

        await self._queue.put((sort_key, counter, row_id, request))
        return True

    async def pop(self) -> Request:
        """Remove and return the next request. Blocks when the queue is empty."""
        assert self._conn is not None, "call open() first"
        _, _, row_id, request = await self._queue.get()
        task = asyncio.current_task()
        self._in_flight[id(task)] = row_id
        with self._conn:
            self._conn.execute("UPDATE queue SET state='in_flight' WHERE id=?", (row_id,))
        return request

    def task_done(self) -> None:
        """Signal that a previously popped request has been processed."""
        assert self._conn is not None, "call open() first"
        task = asyncio.current_task()
        row_id = self._in_flight.pop(id(task), None)
        if row_id is not None:
            with self._conn:
                self._conn.execute("DELETE FROM queue WHERE id=?", (row_id,))
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
        return self._seen_count

    # ------------------------------------------------------------------ #
    # private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _canonical(self, url: str) -> str:
        return canonicalize(url, sort_params=self._sort_params)

    def _sort_key(self, request: Request) -> int:
        if self._strategy == "bfs":
            return self._counter
        if self._strategy == "dfs":
            return -self._counter
        # score: negate so higher priority value leaves the min-heap first
        return -request.priority
