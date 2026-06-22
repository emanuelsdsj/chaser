# Pipeline & Stores

The Pipeline is an async processing chain that every item passes through before being stored. Stages run in order; a stage can transform, filter, or store items.

## Basic usage

```python
from chaser import Engine, JsonlStore, Pipeline

pipeline = Pipeline([JsonlStore("output.jsonl")])
engine = Engine(pipeline=pipeline)
await engine.run(MyTrapper())
```

## Built-in stores

### JsonlStore

Streams items to a newline-delimited JSON file. Each item is one line.

```python
JsonlStore("output.jsonl")
```

### CsvStore

Streams items to a CSV file. Column names are inferred from the first item's fields.

```python
from chaser.pipeline.store.csv import CsvStore

CsvStore("output.csv")
```

### DbStore

Writes items to a database table using async SQLAlchemy. The table is created automatically from the item's fields if it does not exist.

```python
from chaser.pipeline.store.db import DbStore

DbStore("sqlite+aiosqlite:///crawl.db", table="articles")
# or PostgreSQL:
DbStore("postgresql+asyncpg://user:pass@host/db", table="articles")
```

Requires `pip install "chaser[db]"`.

### ParquetStore

Buffers items in memory and writes a single Parquet file on close.

```python
from chaser.pipeline.store.parquet import ParquetStore

ParquetStore("output.parquet")
```

Requires `pip install "chaser[parquet]"`.

## Filtering stages

### DuplicateFilter

Drops items whose key has already been seen in this crawl run.

```python
from chaser.pipeline.filters import DuplicateFilter

pipeline = Pipeline([
    DuplicateFilter(key=lambda item: item.url),
    JsonlStore("output.jsonl"),
])
```

## Dead-letter queue

Pass `dead_letter` to capture items that cause any stage to raise an exception. Each failure is appended as a JSON line with the item payload, stage name, and error message — nothing is silently lost.

```python
pipeline = Pipeline(
    [DuplicateFilter(key=lambda i: i.url), JsonlStore("output.jsonl")],
    dead_letter="failed.jsonl",
)
```

## Writing a custom stage

Subclass `Stage` and override `process`. Return `None` to drop the item.

```python
from chaser import Item
from chaser.pipeline.base import Stage


class PriceFilter(Stage):
    def __init__(self, min_price: float) -> None:
        self._min = min_price

    async def process(self, item: Item) -> Item | None:
        if item.price < self._min:   # type: ignore[attr-defined]
            return None
        return item
```

Use `open` and `close` for resources (file handles, DB connections) that should live for the full crawl:

```python
class AuditStage(Stage):
    async def open(self):
        self._log = open("audit.log", "a")

    async def close(self):
        self._log.close()

    async def process(self, item):
        self._log.write(f"{item}\n")
        return item
```

## Composing multiple stores

Stages run in sequence, so you can fan out to multiple stores at once:

```python
pipeline = Pipeline([
    DuplicateFilter(key=lambda i: i.url),
    JsonlStore("output.jsonl"),   # local backup
    S3Store("my-bucket", "run/output.jsonl"),  # cloud archive
])
```
