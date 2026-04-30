from __future__ import annotations

import pytest

from chaser.item.base import Item
from chaser.item.loader import ItemLoader, compose, first, join, strip, take_all
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response

# ---------------------------------------------------------------------------
# Item fixtures
# ---------------------------------------------------------------------------


class ArticleItem(Item):
    url: str
    title: str
    tags: list[str] = []
    body: str = ""


class SimpleItem(Item):
    name: str


# ---------------------------------------------------------------------------
# Response fixture
# ---------------------------------------------------------------------------

_HTML = """
<html><body>
  <h1>  Hello World  </h1>
  <p class="body">First paragraph.</p>
  <p class="body">Second paragraph.</p>
  <span class="tag">python</span>
  <span class="tag">asyncio</span>
  <span class="tag">  </span>
</body></html>
"""


def _response(url: str = "https://example.com/article") -> Response:
    req = Request(url=url)
    return Response(
        url=url,
        status=200,
        headers=Headers({"content-type": "text/html; charset=utf-8"}),
        body=_HTML.encode(),
        request=req,
    )


# ---------------------------------------------------------------------------
# Processors
# ---------------------------------------------------------------------------


def test_strip_removes_whitespace() -> None:
    assert strip(["  hello  ", " world ", "  "]) == ["hello", "world"]


def test_strip_discards_blank_strings() -> None:
    assert strip(["", "  ", "\t"]) == []


def test_join_default_sep() -> None:
    assert join()(["a", "b", "c"]) == "a b c"


def test_join_custom_sep() -> None:
    assert join(", ")(["x", "y"]) == "x, y"


def test_join_skips_empty() -> None:
    assert join()([" a", "", "b "]) == " a b "


def test_first_returns_first() -> None:
    assert first()([10, 20, 30]) == 10


def test_first_returns_default_when_empty() -> None:
    assert first(default="n/a")([]) == "n/a"


def test_first_default_is_none() -> None:
    assert first()([]) is None


def test_take_all_returns_list() -> None:
    assert take_all(["a", "b"]) == ["a", "b"]


def test_compose_chains_processors() -> None:
    pipeline = compose(strip, first())
    result = pipeline(["  hello  ", "  world  "])
    assert result == "hello"


def test_compose_single_processor() -> None:
    assert compose(strip)(["  x  ", ""]) == ["x"]


# ---------------------------------------------------------------------------
# ItemLoader — add_value
# ---------------------------------------------------------------------------


def test_add_value_scalar() -> None:
    loader = ItemLoader(SimpleItem)
    loader.add_value("name", "Alice")
    item = loader.load()
    assert item.name == "Alice"


def test_add_value_list() -> None:
    loader = ItemLoader(ArticleItem)
    loader.add_value("url", "https://example.com")
    loader.add_value("title", "Test")
    loader.add_value("tags", ["a", "b"])
    item = loader.load()
    assert item.tags == ["a", "b"]


def test_add_value_with_processor() -> None:
    class MultiItem(Item):
        name: list[str]

    loader = ItemLoader(MultiItem)
    loader.add_value("name", ["  Alice  ", "  Bob  "], processor=strip)
    item = loader.load()
    assert item.name == ["Alice", "Bob"]  # type: ignore[attr-defined]


def test_multiple_add_value_accumulates() -> None:
    loader = ItemLoader(ArticleItem)
    loader.add_value("url", "https://example.com")
    loader.add_value("title", "T")
    loader.add_value("tags", "python")
    loader.add_value("tags", "asyncio")
    item = loader.load()
    assert item.tags == ["python", "asyncio"]


# ---------------------------------------------------------------------------
# ItemLoader — add_css / add_xpath
# ---------------------------------------------------------------------------


def test_add_css_extracts_text() -> None:
    resp = _response()
    loader = ItemLoader(ArticleItem, response=resp)
    loader.add_value("url", resp.url)
    loader.add_css("title", "h1::text", processor=compose(strip, first()))
    loader.add_value("tags", [])
    item = loader.load()
    assert item.title == "Hello World"


def test_add_css_multiple_values() -> None:
    resp = _response()
    loader = ItemLoader(ArticleItem, response=resp)
    loader.add_value("url", resp.url)
    loader.add_value("title", "T")
    loader.add_css("tags", "span.tag::text", processor=strip)
    item = loader.load()
    assert item.tags == ["python", "asyncio"]


def test_add_xpath_extracts_text() -> None:
    resp = _response()
    loader = ItemLoader(ArticleItem, response=resp)
    loader.add_value("url", resp.url)
    loader.add_xpath("title", "//h1/text()", processor=compose(strip, first()))
    loader.add_value("tags", [])
    item = loader.load()
    assert item.title == "Hello World"


def test_add_css_no_response_raises() -> None:
    loader = ItemLoader(SimpleItem)
    with pytest.raises(RuntimeError, match="requires a response"):
        loader.add_css("name", "h1::text")


def test_add_xpath_no_response_raises() -> None:
    loader = ItemLoader(SimpleItem)
    with pytest.raises(RuntimeError, match="requires a response"):
        loader.add_xpath("name", "//h1/text()")


# ---------------------------------------------------------------------------
# ItemLoader — get_collected / load edge cases
# ---------------------------------------------------------------------------


def test_get_collected_returns_accumulated() -> None:
    loader = ItemLoader(SimpleItem)
    loader.add_value("name", "a")
    loader.add_value("name", "b")
    assert loader.get_collected("name") == ["a", "b"]


def test_get_collected_unknown_field_returns_empty() -> None:
    loader = ItemLoader(SimpleItem)
    assert loader.get_collected("nonexistent") == []


def test_load_unwraps_single_element_list() -> None:
    loader = ItemLoader(SimpleItem)
    loader.add_value("name", "Alice")
    item = loader.load()
    assert isinstance(item.name, str)
    assert item.name == "Alice"
