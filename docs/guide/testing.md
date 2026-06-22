# Testing

Chaser ships a `testing` module with helpers that let you unit-test Trappers without making real HTTP requests.

## FakeResponse

`FakeResponse` creates a `Response` object from a string of HTML (or JSON). Use it to feed your parse methods controlled input.

```python
from chaser.testing import FakeResponse

response = FakeResponse(
    url="https://example.com/article/1",
    html="<h1>Hello</h1><p class='body'>World</p>",
)

# All the usual response methods work
assert response.selector.css("h1::text").get() == "Hello"
assert response.status == 200
assert response.ok
```

For JSON responses:

```python
response = FakeResponse(
    url="https://api.example.com/items",
    body=b'{"count": 3, "items": []}',
    headers={"Content-Type": "application/json"},
)
assert response.json() == {"count": 3, "items": []}
```

## assert_items

`assert_items` runs a parse method and checks that it yields exactly the expected items — in any order by default.

```python
import pytest
from chaser.testing import FakeResponse, assert_items


class QuoteItem(Item):
    text: str
    author: str


class QuoteTrapper(Trapper):
    start_urls = ["https://quotes.toscrape.com"]

    async def parse(self, response):
        for quote in response.selector.css("div.quote"):
            yield QuoteItem(
                text=quote.css("span.text::text").get(""),
                author=quote.css("small.author::text").get(""),
            )


@pytest.mark.asyncio
async def test_parse_quotes():
    html = """
        <div class="quote">
            <span class="text">The only way out is through.</span>
            <small class="author">Robert Frost</small>
        </div>
        <div class="quote">
            <span class="text">Stay hungry, stay foolish.</span>
            <small class="author">Steve Jobs</small>
        </div>
    """
    response = FakeResponse(url="https://quotes.toscrape.com", html=html)
    await assert_items(QuoteTrapper(), response, [
        QuoteItem(text="The only way out is through.", author="Robert Frost"),
        QuoteItem(text="Stay hungry, stay foolish.", author="Steve Jobs"),
    ])
```

If the actual items don't match the expected ones, `assert_items` raises `AssertionError` with a diff.

## Testing follow-up requests

`assert_items` returns a tuple of `(items, requests)` — you can check the follow-up requests too:

```python
@pytest.mark.asyncio
async def test_pagination():
    html = """
        <div class="quote"><span class="text">...</span><small class="author">...</small></div>
        <li class="next"><a href="/page/2/">Next</a></li>
    """
    response = FakeResponse(url="https://quotes.toscrape.com", html=html)
    items, requests = await assert_items(QuoteTrapper(), response, expected_count=1)
    assert len(requests) == 1
    assert requests[0].url == "https://quotes.toscrape.com/page/2/"
```

## pytest configuration

Chaser tests use `pytest-asyncio` in auto mode. Add this to your `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## Testing the pipeline

Test pipeline stages in isolation by calling `process` directly:

```python
from chaser.pipeline.filters import DuplicateFilter


@pytest.mark.asyncio
async def test_duplicate_filter():
    f = DuplicateFilter(key=lambda i: i.url)
    item = ArticleItem(url="https://example.com", title="A")

    result1 = await f.process(item)
    assert result1 is item            # first time — passes through

    result2 = await f.process(item)
    assert result2 is None            # duplicate — dropped
```
