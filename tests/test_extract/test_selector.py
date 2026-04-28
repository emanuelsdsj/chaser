from __future__ import annotations

import re

import pytest

from chaser.extract.selector import Selector
from chaser.net.headers import Headers
from chaser.net.response import Response

HTML = """
<html>
  <head><title>Test page</title></head>
  <body>
    <h1 class="main-title">Hello world</h1>
    <ul id="links">
      <li><a href="/one">One</a></li>
      <li><a href="/two">Two</a></li>
      <li><a href="/three">Three</a></li>
    </ul>
    <p class="price">Price: $42.99</p>
    <img src="/logo.png" alt="Logo" />
  </body>
</html>
"""


@pytest.fixture()
def sel() -> Selector:
    return Selector(HTML)


# ---------------------------------------------------------------------------
# Selector — CSS
# ---------------------------------------------------------------------------


def test_css_get_text(sel: Selector) -> None:
    assert sel.css("h1::text").get() == "Hello world"


def test_css_getall_text(sel: Selector) -> None:
    texts = sel.css("li a::text").getall()
    assert texts == ["One", "Two", "Three"]


def test_css_get_attr(sel: Selector) -> None:
    assert sel.css("a::attr(href)").get() == "/one"


def test_css_getall_attr(sel: Selector) -> None:
    hrefs = sel.css("a::attr(href)").getall()
    assert hrefs == ["/one", "/two", "/three"]


def test_css_no_match_returns_default(sel: Selector) -> None:
    assert sel.css("span::text").get() is None
    assert sel.css("span::text").get(default="fallback") == "fallback"


def test_css_chaining(sel: Selector) -> None:
    texts = sel.css("ul#links").css("a::text").getall()
    assert texts == ["One", "Two", "Three"]


# ---------------------------------------------------------------------------
# Selector — XPath
# ---------------------------------------------------------------------------


def test_xpath_get_text(sel: Selector) -> None:
    assert sel.xpath("//h1/text()").get() == "Hello world"


def test_xpath_getall(sel: Selector) -> None:
    texts = sel.xpath("//li/a/text()").getall()
    assert texts == ["One", "Two", "Three"]


def test_xpath_chaining(sel: Selector) -> None:
    hrefs = sel.css("ul").xpath(".//a/@href").getall()
    assert hrefs == ["/one", "/two", "/three"]


# ---------------------------------------------------------------------------
# Selector — regex
# ---------------------------------------------------------------------------


def test_re_extracts_matches(sel: Selector) -> None:
    matches = sel.css("p.price::text").re(r"\$[\d.]+")
    assert matches == ["$42.99"]


def test_re_first_returns_first(sel: Selector) -> None:
    first = sel.css("a::attr(href)").re_first(r"/\w+")
    assert first == "/one"


def test_re_compiled_pattern(sel: Selector) -> None:
    pattern = re.compile(r"\d+\.\d+")
    matches = sel.css("p.price::text").re(pattern)
    assert matches == ["42.99"]


# ---------------------------------------------------------------------------
# Selector — attrib
# ---------------------------------------------------------------------------


def test_selector_attrib_property(sel: Selector) -> None:
    img = sel.css("img")[0]
    assert img.attrib["src"] == "/logo.png"
    assert img.attrib["alt"] == "Logo"


def test_selector_list_attrib_first(sel: Selector) -> None:
    attrib = sel.css("a").attrib
    assert attrib["href"] == "/one"


# ---------------------------------------------------------------------------
# SelectorList — iteration and length
# ---------------------------------------------------------------------------


def test_selectorlist_len(sel: Selector) -> None:
    assert len(sel.css("li")) == 3


def test_selectorlist_bool(sel: Selector) -> None:
    assert sel.css("h1")
    assert not sel.css("section")


def test_selectorlist_iteration_yields_selectors(sel: Selector) -> None:
    items = list(sel.css("li"))
    assert all(isinstance(s, Selector) for s in items)
    assert len(items) == 3


# ---------------------------------------------------------------------------
# from_response + Response.selector
# ---------------------------------------------------------------------------


def _make_response(html: str) -> Response:
    return Response(
        url="https://example.com/page",
        status=200,
        headers=Headers({"content-type": "text/html"}),
        body=html.encode(),
    )


def test_from_response(sel: Selector) -> None:
    resp = _make_response(HTML)
    s = Selector.from_response(resp)
    assert s.css("h1::text").get() == "Hello world"


def test_response_selector_property() -> None:
    resp = _make_response(HTML)
    assert resp.selector.css("title::text").get() == "Test page"


def test_response_selector_is_selector_instance() -> None:
    resp = _make_response(HTML)
    assert isinstance(resp.selector, Selector)
