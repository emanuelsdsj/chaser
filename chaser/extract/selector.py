from __future__ import annotations

import re as _re
from typing import TYPE_CHECKING, Any

import parsel

if TYPE_CHECKING:
    from chaser.net.response import Response


class SelectorList:
    """A sequence of Selectors with chainable CSS/XPath methods.

    Mirrors parsel's API so existing muscle memory transfers over.
    Wraps the inner SelectorList to keep chaser types in the return values.
    """

    def __init__(self, inner: parsel.SelectorList) -> None:  # type: ignore[type-arg]
        self._inner = inner

    def css(self, query: str) -> SelectorList:
        return SelectorList(self._inner.css(query))

    def xpath(self, query: str, **kwargs: Any) -> SelectorList:
        return SelectorList(self._inner.xpath(query, **kwargs))

    def get(self, default: str | None = None) -> str | None:
        return self._inner.get(default=default)

    def getall(self) -> list[str]:
        return self._inner.getall()

    def re(self, pattern: str | _re.Pattern[str]) -> list[str]:
        return self._inner.re(pattern)

    def re_first(
        self,
        pattern: str | _re.Pattern[str],
        default: str | None = None,
    ) -> str | None:
        return self._inner.re_first(pattern, default=default)

    @property
    def attrib(self) -> dict[str, str]:
        """Attributes of the first element, or empty dict if the list is empty."""
        return dict(self._inner.attrib)

    def __getitem__(self, index: int) -> Selector:
        return Selector(self._inner[index])

    def __iter__(self) -> Any:
        for sel in self._inner:
            yield Selector(sel)

    def __len__(self) -> int:
        return len(self._inner)

    def __bool__(self) -> bool:
        return len(self._inner) > 0

    def __repr__(self) -> str:
        return f"<SelectorList ({len(self)} elements)>"


class Selector:
    """CSS + XPath selector backed by parsel.

    Create from an HTML string or from a Response directly::

        sel = Selector("<html><body><h1>Title</h1></body></html>")
        sel = Selector.from_response(response)

        sel.css("h1::text").get()        # "Title"
        sel.xpath("//h1/text()").get()   # "Title"
    """

    def __init__(
        self,
        text_or_inner: str | parsel.Selector,
        *,
        base_url: str = "",
        encoding: str = "utf-8",
        type: str = "html",  # noqa: A002
    ) -> None:
        if isinstance(text_or_inner, parsel.Selector):
            self._inner = text_or_inner
        else:
            self._inner = parsel.Selector(
                text=text_or_inner,
                base_url=base_url,
                encoding=encoding,
                type=type,
            )

    @classmethod
    def from_response(cls, response: Response) -> Selector:
        return cls(response.text, base_url=response.url)

    def css(self, query: str) -> SelectorList:
        return SelectorList(self._inner.css(query))

    def xpath(self, query: str, **kwargs: Any) -> SelectorList:
        return SelectorList(self._inner.xpath(query, **kwargs))

    def jmespath(self, query: str, **kwargs: Any) -> SelectorList:
        """Query JSON data using JMESPath syntax.

        Only meaningful on selectors created with ``type="json"`` (e.g. via
        ``response.json_selector``).

            sel = response.json_selector
            sel.jmespath("items[*].name").getall()
        """
        return SelectorList(self._inner.jmespath(query, **kwargs))

    def re(self, pattern: str | _re.Pattern[str]) -> list[str]:
        return self._inner.re(pattern)

    def re_first(
        self,
        pattern: str | _re.Pattern[str],
        default: str | None = None,
    ) -> str | None:
        return self._inner.re_first(pattern, default=default)

    @property
    def attrib(self) -> dict[str, str]:
        return dict(self._inner.attrib)

    def get(self, default: str | None = None) -> str | None:
        result: str | None = self._inner.get()
        return result if result is not None else default

    def getall(self) -> list[str]:
        return self._inner.getall()

    def __repr__(self) -> str:
        return f"<Selector ({self._inner.type})>"
