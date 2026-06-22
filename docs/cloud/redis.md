# Redis Frontier

The default in-memory frontier and the SQLite frontier are single-process. For crawls that span multiple machines or processes, use the `RedisFrontier` — all workers connect to the same Redis server and coordinate atomically.

## Setup

```bash
pip install "chaser[redis]"
```

Pass the Redis URL to the Engine:

```python
engine = Engine(frontier_redis="redis://localhost:6379")
await engine.run(MyTrapper())
```

Multiple processes running the same command connect to the same frontier — each process contributes workers to the shared queue.

## How it works

| Operation | Redis structure |
|-----------|----------------|
| Deduplication | `HSETNX` on a hash — atomic check-and-mark per URL |
| Queue | Sorted set (`ZADD` / `BZPOPMIN`) — score encodes BFS/DFS/priority |
| In-flight tracking | Hash — maps slot ID → request payload |
| Crash recovery | On startup, in-flight requests are moved back to the queue |

### Scheduling strategies

The `strategy` parameter controls how the sorted set score is computed:

| Strategy | Behaviour |
|----------|-----------|
| `bfs` (default) | Insertion counter as score — breadth-first |
| `dfs` | Negative insertion counter — depth-first |
| `score` | Negative `request.priority` — higher priority fetched first |

## Configuration

```python
from chaser.frontier.redis_frontier import RedisFrontier

frontier = RedisFrontier(
    redis_url="redis://localhost:6379",
    prefix="myproject",    # namespace for Redis keys (avoids collisions)
    strategy="bfs",
    sort_params=False,     # whether to sort query string params during canonicalization
    clear=False,           # True → wipe all keys on open() and start fresh
)
```

To use a custom-configured frontier directly:

```python
frontier = RedisFrontier("redis://myhost:6379", prefix="crawl-2024")
engine = Engine(frontier_redis="redis://myhost:6379")  # or pass frontier_redis
```

## Crash recovery

When a process dies mid-crawl, requests that were in-flight (popped but not acknowledged) are automatically moved back to the pending queue the next time any process calls `open()`. No manual intervention needed.

## Multi-process example

Run as many worker processes as you need — they all share the same frontier:

```bash
# Terminal 1
CHASER_CONCURRENCY=16 python worker.py

# Terminal 2
CHASER_CONCURRENCY=16 python worker.py

# Terminal 3 — more workers on a different machine
CHASER_CONCURRENCY=8 python worker.py
```

```python
# worker.py
import asyncio
from chaser import Engine
from myproject.trappers import MyTrapper

async def main():
    engine = Engine(
        concurrency=16,
        frontier_redis="redis://redis-host:6379",
    )
    await engine.run(MyTrapper())

asyncio.run(main())
```

## Key namespacing

Each `RedisFrontier` uses a `prefix` to namespace its Redis keys:

- `{prefix}:seen` — dedup hash
- `{prefix}:queue` — sorted set of pending requests
- `{prefix}:counter` — monotonic counter for BFS/DFS ordering
- `{prefix}:inflight` — crash recovery hash

Use a different `prefix` for each concurrent crawl project to avoid collisions.
