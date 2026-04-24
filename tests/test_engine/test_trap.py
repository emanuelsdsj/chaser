from __future__ import annotations

import pytest

from chaser.engine import trap
from chaser.item.base import Item
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.base import Trapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response(url: str = "http://example.com", body: bytes = b"") -> Response:
    from chaser.net.headers import Headers

    return Response(url=url, status=200, headers=Headers(), body=body)


class _LinkItem(Item):
    url: str


class _OkTrpper(Trapper):
    name = "ok"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        yield _LinkItem(url=response.url)
        yield Request(url="http://next.com")


class _RaisingTrpper(Trapper):
    name = "raising"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        yield _LinkItem(url=response.url)
        raise RuntimeError("parse blew up")


class _EmptyTrpper(Trapper):
    name = "empty"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        return
        yield  # pragma: no cover — makes this an async generator


class _CallbackTrpper(Trapper):
    name = "callbacks"
    start_urls: list[str] = []

    async def parse(self, response: Response):  # type: ignore[override]
        yield _LinkItem(url="default")

    async def parse_detail(self, response: Response):  # type: ignore[misc]
        yield _LinkItem(url="detail")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTrapExecute:
    async def test_yields_items_and_requests(self) -> None:
        trapper = _OkTrpper()
        results = [r async for r in trap.execute(trapper, _response())]

        assert len(results) == 2
        assert isinstance(results[0], _LinkItem)
        assert results[0].url == "http://example.com"
        assert isinstance(results[1], Request)
        assert results[1].url == "http://next.com"

    async def test_exception_is_caught_not_propagated(self) -> None:
        trapper = _RaisingTrpper()
        # Should not raise — exception is swallowed inside execute()
        results = [r async for r in trap.execute(trapper, _response())]
        # The item yielded before the exception still comes through
        assert len(results) == 1
        assert isinstance(results[0], _LinkItem)

    async def test_missing_callback_yields_nothing(self) -> None:
        trapper = _OkTrpper()
        results = [r async for r in trap.execute(trapper, _response(), callback="nonexistent")]
        assert results == []

    async def test_default_callback_is_parse(self) -> None:
        trapper = _OkTrpper()
        results = [r async for r in trap.execute(trapper, _response(), callback=None)]
        assert len(results) == 2

    async def test_custom_callback_routes_correctly(self) -> None:
        trapper = _CallbackTrpper()

        default_results = [r async for r in trap.execute(trapper, _response())]
        detail_results = [
            r async for r in trap.execute(trapper, _response(), callback="parse_detail")
        ]

        assert default_results[0].url == "default"  # type: ignore[union-attr]
        assert detail_results[0].url == "detail"  # type: ignore[union-attr]

    async def test_empty_parse_yields_nothing(self) -> None:
        trapper = _EmptyTrpper()
        results = [r async for r in trap.execute(trapper, _response())]
        assert results == []

    async def test_exception_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        trapper = _RaisingTrpper()
        with caplog.at_level(logging.ERROR, logger="chaser.engine.trap"):
            _ = [r async for r in trap.execute(trapper, _response())]

        assert any("parse blew up" in r.message or "Unhandled" in r.message for r in caplog.records)
