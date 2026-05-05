from __future__ import annotations

from typing import Any

from chaser.item.base import Item
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.base import Trapper


def FakeResponse(
    url: str,
    html: str = "",
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    encoding: str = "utf-8",
    meta: dict[str, Any] | None = None,
) -> Response:
    """Build a Response without making any HTTP requests.

    Designed for unit-testing trappers — pass it to ``trapper.parse()``
    or use with :func:`assert_items` / :func:`collect_parse`.

    Example::

        from chaser.testing import FakeResponse, assert_items

        async def test_my_trapper():
            response = FakeResponse("https://example.com", "<h1>Hello</h1>")
            await assert_items(MyTrapper(), response, [{"title": "Hello"}])
    """
    req = Request(url=url, meta=meta or {})
    h = Headers(
        {
            "content-type": f"text/html; charset={encoding}",
            **(headers or {}),
        }
    )
    return Response(
        url=url,
        status=status,
        headers=h,
        body=html.encode(encoding),
        encoding=encoding,
        request=req,
    )


async def collect_parse(
    trapper: Trapper,
    response: Response,
    callback: str | None = None,
) -> tuple[list[Request], list[Item]]:
    """Run ``trapper.parse(response)`` and separate results into requests and items.

    Returns a ``(requests, items)`` tuple. Unexpected types are silently ignored
    since they'd be logged-and-skipped by the Engine anyway.
    """
    from chaser.engine import trap

    requests: list[Request] = []
    items: list[Item] = []
    async for result in trap.execute(trapper, response, callback):
        if isinstance(result, Request):
            requests.append(result)
        elif isinstance(result, Item):
            items.append(result)
    return requests, items


async def assert_items(
    trapper: Trapper,
    response: Response,
    expected: list[dict[str, Any]],
) -> None:
    """Assert that ``trapper.parse(response)`` yields items matching *expected*.

    Each dict in *expected* is checked against the corresponding item via
    attribute access. Order matters. Use :func:`collect_parse` directly when
    you need the actual item objects or want to check requests too.

    Example::

        await assert_items(
            MyTrapper(),
            FakeResponse("https://example.com", "<h1>Hello</h1>"),
            [{"title": "Hello", "url": "https://example.com"}],
        )
    """
    _, items = await collect_parse(trapper, response)

    assert len(items) == len(expected), (
        f"Expected {len(expected)} item(s), got {len(items)}: {items!r}"
    )
    for i, (item, exp) in enumerate(zip(items, expected, strict=True)):
        for key, value in exp.items():
            actual = getattr(item, key, None)
            assert actual == value, f"Item[{i}].{key}: expected {value!r}, got {actual!r}"
