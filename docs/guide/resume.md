# Crawl Resume

Long crawls crash. Servers go down, processes get killed, machines run out of power. The SQLite frontier persists every URL seen and every URL pending so you can pick up exactly where things stopped.

## Enable resume

Pass `frontier_db` to the Engine:

```python
engine = Engine(frontier_db="crawl.db")
await engine.run(MyTrapper())
```

On the **first run**, Chaser creates `crawl.db` and writes all frontier state to it.

On the **next run** with the same `frontier_db` path:
- URLs already visited are skipped (the seen set is restored from the DB)
- URLs that were pending but not yet fetched are re-queued
- URLs that were in-flight when the process died are moved back to pending automatically

No duplicates, no gaps.

## What gets persisted

| State | Storage |
|-------|---------|
| Seen URLs (bloom key + canonical form) | SQLite `seen` table |
| Pending queue | SQLite `queue` table |
| In-flight requests (crash recovery) | SQLite `inflight` table |

## Starting fresh

Delete the database file between runs to start a clean crawl:

```bash
rm crawl.db
```

Or rename it to archive the previous crawl state before starting a new one.

## Combining with the pipeline

Resume works independently of the pipeline. Items already extracted in a previous run are not re-extracted (because the URLs are already in the seen set), but the pipeline state (e.g. a JSONL file) accumulates across runs. If you need idempotent output, add a `DuplicateFilter` to the pipeline keyed on a stable item identifier.

```python
from chaser.pipeline.filters import DuplicateFilter

pipeline = Pipeline([
    DuplicateFilter(key=lambda i: i.url),
    JsonlStore("output.jsonl"),
])
engine = Engine(frontier_db="crawl.db", pipeline=pipeline)
```

## Distributed resume with Redis

For multi-process crawls, use the [Redis Frontier](../cloud/redis.md) instead. It provides the same crash recovery guarantees over a shared Redis backend that all worker processes connect to.
