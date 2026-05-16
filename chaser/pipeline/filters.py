from __future__ import annotations

from collections.abc import Callable, Hashable

from chaser.item.base import Item
from chaser.pipeline.base import Stage


class DuplicateFilter(Stage):
    """Drop items whose key has already been seen in this crawl.

    Pass a function that extracts a hashable key from each item. Items with
    a key seen before are silently dropped — they never reach later stages.

    Example::

        pipeline = Pipeline([
            DuplicateFilter(key=lambda i: i.url),
            JsonlStore("out.jsonl"),
        ])

    The default key is the item itself (identity), which works when items
    implement ``__hash__`` and ``__eq__`` via Pydantic's model equality.
    """

    def __init__(self, key: Callable[[Item], Hashable] = lambda i: i.model_dump_json()) -> None:
        self._key = key
        self._seen: set[Hashable] = set()

    async def process(self, item: Item) -> Item | None:
        k = self._key(item)
        if k in self._seen:
            return None
        self._seen.add(k)
        return item
