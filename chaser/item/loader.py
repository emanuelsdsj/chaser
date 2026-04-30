from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaser.item.base import Item
    from chaser.net.response import Response

Processor = Callable[[list[Any]], Any]


def strip(values: list[str]) -> list[str]:
    """Remove leading/trailing whitespace; discard empty strings."""
    return [v.strip() for v in values if v.strip()]


def join(sep: str = " ") -> Processor:
    """Collapse all values into a single string separated by ``sep``."""

    def _join(values: list[str]) -> str:
        return sep.join(v for v in values if v)

    return _join


def first(default: Any = None) -> Processor:
    """Return the first collected value, or ``default`` when empty."""

    def _first(values: list[Any]) -> Any:
        return values[0] if values else default

    return _first


def take_all(values: list[Any]) -> list[Any]:
    """Return all collected values as a list (identity for lists)."""
    return values


def compose(*processors: Processor) -> Processor:
    """Chain processors left-to-right: each receives the output of the previous."""

    def _composed(values: list[Any]) -> Any:
        current: Any = values
        for p in processors:
            if not isinstance(current, list):
                current = [current]
            current = p(current)
        return current

    return _composed


class ItemLoader:
    """Accumulates extracted values per field and builds a Pydantic Item.

    Processors transform the raw list of extracted strings into the final
    field value before the item is constructed.

    Example::

        loader = ItemLoader(ArticleItem, response=response)
        loader.add_css("title", "h1::text", processor=first())
        loader.add_css("tags", ".tag::text", processor=strip)
        loader.add_value("url", response.url)
        item = loader.load()
    """

    def __init__(
        self,
        item_class: type[Item],
        response: Response | None = None,
    ) -> None:
        self._item_class = item_class
        self._response = response
        self._values: dict[str, list[Any]] = {}

    # ------------------------------------------------------------------
    # Public add methods
    # ------------------------------------------------------------------

    def add_value(self, field: str, value: Any, *, processor: Processor | None = None) -> None:
        """Add a raw value (or list of values) directly."""
        raw = value if isinstance(value, list) else [value]
        self._accumulate(field, raw, processor)

    def add_css(
        self,
        field: str,
        query: str,
        *,
        processor: Processor | None = None,
    ) -> None:
        """Extract values using a CSS selector and add them to *field*."""
        if self._response is None:
            raise RuntimeError("ItemLoader.add_css requires a response — pass one to __init__")
        raw = self._response.selector.css(query).getall()
        self._accumulate(field, raw, processor)

    def add_xpath(
        self,
        field: str,
        query: str,
        *,
        processor: Processor | None = None,
    ) -> None:
        """Extract values using an XPath query and add them to *field*."""
        if self._response is None:
            raise RuntimeError("ItemLoader.add_xpath requires a response — pass one to __init__")
        raw = self._response.selector.xpath(query).getall()
        self._accumulate(field, raw, processor)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def get_collected(self, field: str) -> list[Any]:
        """Return the raw accumulated values for *field* (before load)."""
        return list(self._values.get(field, []))

    def load(self) -> Item:
        """Apply final defaults and instantiate the item.

        Single-element lists are unwrapped to scalars automatically.
        Use ``processor=take_all`` on a field to keep it as a list.
        """
        data: dict[str, Any] = {}
        for field, values in self._values.items():
            data[field] = values[0] if len(values) == 1 else values
        return self._item_class(**data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _accumulate(self, field: str, raw: list[Any], processor: Processor | None) -> None:
        if field not in self._values:
            self._values[field] = []

        if processor is not None:
            result = processor(raw)
            if isinstance(result, list):
                self._values[field].extend(result)
            else:
                self._values[field].append(result)
        else:
            self._values[field].extend(raw)
