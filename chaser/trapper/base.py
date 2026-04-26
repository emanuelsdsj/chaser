from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaser.net.response import Response

# Avoid importing Request/Item at module level to keep the dependency graph
# clean — the engine does the isinstance checks, not this module.
ParseYield = Any


class Trapper(ABC):
    """Base class for user-defined crawlers.

    Subclass, set ``start_urls``, and implement ``parse()``.
    Pass an instance (or a list) to ``Engine.run()``.

    Class-level ``name`` is auto-derived from the class name if not set
    explicitly — no boilerplate required for the common case.
    """

    name: str = ""
    start_urls: list[str] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only set the name if the subclass didn't declare one itself
        if not cls.__dict__.get("name"):
            cls.name = cls.__name__.lower()

    def start_requests(self) -> list[Any]:
        """Produce initial requests from ``start_urls``.

        Override this to add custom headers, meta, or priority to seed requests.
        """
        from chaser.net.request import Request

        return [Request(url=url, meta={"trapper": self.name}) for url in self.start_urls]

    @abstractmethod
    async def parse(self, response: Response) -> AsyncIterator[ParseYield]:
        """Parse a response and yield ``Item`` and/or ``Request`` objects.

        Implementations should be async generators::

            async def parse(self, response):
                yield ArticleItem(url=response.url, title=...)
                yield Request(url=next_page_url)
        """
        yield  # pragma: no cover — marks this as an async generator stub
