from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Item(BaseModel):
    """Base class for all crawl output.

    Subclass and declare typed fields. Pydantic validates on instantiation
    and serializes to dict/JSON for free.

    Example::

        class ArticleItem(Item):
            url: str
            title: str
            body: str = ""
    """

    model_config = ConfigDict(extra="forbid")
