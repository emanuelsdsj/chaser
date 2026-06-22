# Items & Loaders

## Defining an Item

Items are Pydantic v2 models. Define fields with standard Python type hints — Pydantic validates every item before it reaches the pipeline.

```python
from chaser import Item


class ArticleItem(Item):
    url: str
    title: str
    author: str
    tags: list[str] = []
    published_at: str | None = None
```

Items with missing required fields or wrong types raise a `ValidationError` immediately, so invalid data never silently reaches your store.

## Yielding items

Return items from any `parse` method:

```python
async def parse(self, response):
    yield ArticleItem(
        url=response.url,
        title=response.selector.css("h1::text").get(""),
        author=response.selector.css(".author::text").get(""),
        tags=response.selector.css(".tag::text").getall(),
    )
```

## ItemLoader

For pages where raw selector output needs cleaning before it fits your schema, use `ItemLoader`. It lets you attach processor functions to each field.

```python
from chaser import Item, ItemLoader, compose, first, join, strip


class ArticleItem(Item):
    url: str
    title: str
    body: str
    tags: list[str]


class ArticleTrapper(Trapper):
    async def parse(self, response):
        loader = ItemLoader(ArticleItem, response=response)
        loader.add_value("url", response.url)
        loader.add_css("title", "h1::text", processor=compose(strip, first()))
        loader.add_css("body", ".content p::text", processor=join("\n"))
        loader.add_css("tags", ".tag::text", processor=strip)
        yield loader.load()
```

### Built-in processors

| Processor | What it does |
|-----------|--------------|
| `strip` | Strips leading/trailing whitespace from each string in the list |
| `first()` | Returns the first element, or a default if the list is empty |
| `join(sep)` | Joins all list elements into one string with `sep` |
| `take_all` | Identity — returns the full list (default for list fields) |
| `compose(*fns)` | Chains multiple processors left-to-right |

### add_css / add_xpath / add_value

```python
loader.add_css("title", "h1::text")             # CSS selector
loader.add_xpath("author", "//span[@class='by']/text()")  # XPath
loader.add_value("url", response.url)           # literal value
```

Multiple calls to the same field name accumulate values:

```python
loader.add_css("tags", ".tag::text")
loader.add_css("tags", ".category::text")
# tags receives the union of both lists before the processor runs
```

### Writing a custom processor

A processor is any callable that takes a list and returns a value:

```python
def dollar_to_float(values: list[str]) -> float:
    raw = values[0].replace("$", "").replace(",", "").strip()
    return float(raw)

loader.add_css("price", ".price::text", processor=dollar_to_float)
```
