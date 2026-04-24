from __future__ import annotations

import httpx
import respx

from chaser.engine.runner import Engine
from chaser.item.base import Item
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.base import Trapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _PageItem(Item):
    url: str
    status: int


class _SimpleTrpper(Trapper):
    """Fetches start_urls and yields one item per response."""

    name = "simple"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        yield _PageItem(url=response.url, status=response.status)


class _FollowTrpper(Trapper):
    """First page yields an item + a follow-up request. Second page just an item."""

    name = "follow"

    def __init__(self, start: str, follow: str) -> None:
        self.start_urls = [start]
        self._follow = follow

    async def parse(self, response: Response):  # type: ignore[override]
        yield _PageItem(url=response.url, status=response.status)
        if response.url == self.start_urls[0]:
            yield Request(url=self._follow)


class _DupeTrpper(Trapper):
    """Yields the same follow-up URL twice — should only be fetched once."""

    name = "dupe"

    def __init__(self, start: str, dupe_url: str) -> None:
        self.start_urls = [start]
        self._dupe_url = dupe_url

    async def parse(self, response: Response):  # type: ignore[override]
        if response.url == self.start_urls[0]:
            yield Request(url=self._dupe_url)
            yield Request(url=self._dupe_url)  # duplicate — should be dropped


class _CallbackTrpper(Trapper):
    """Uses a custom callback on a sub-request."""

    name = "cbtrapper"

    def __init__(self, start: str, detail: str) -> None:
        self.start_urls = [start]
        self._detail = detail

    async def parse(self, response: Response):  # type: ignore[override]
        yield Request(url=self._detail, callback="parse_detail")

    async def parse_detail(self, response: Response):  # type: ignore[misc]
        yield _PageItem(url=response.url, status=response.status)


class _RaisingTrpper(Trapper):
    """Parse always raises — engine must not crash."""

    name = "raising"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        raise ValueError("intentional parse error")
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEngineRun:
    @respx.mock
    async def test_simple_crawl_returns_items(self) -> None:
        respx.get("http://example.com/").mock(
            return_value=httpx.Response(200, content=b"hello")
        )
        engine = Engine(concurrency=1, http2=False)
        items = await engine.run(_SimpleTrpper(["http://example.com/"]))

        assert len(items) == 1
        assert isinstance(items[0], _PageItem)
        assert items[0].status == 200

    @respx.mock
    async def test_empty_start_urls_returns_empty(self) -> None:
        engine = Engine(concurrency=1, http2=False)
        items = await engine.run(_SimpleTrpper([]))
        assert items == []

    @respx.mock
    async def test_follow_up_requests_are_fetched(self) -> None:
        respx.get("http://page1.com/").mock(return_value=httpx.Response(200, content=b""))
        respx.get("http://page2.com/").mock(return_value=httpx.Response(200, content=b""))

        engine = Engine(concurrency=2, http2=False)
        items = await engine.run(_FollowTrpper("http://page1.com/", "http://page2.com/"))

        urls = {i.url for i in items}  # type: ignore[union-attr]
        assert "http://page1.com/" in urls
        assert "http://page2.com/" in urls

    @respx.mock
    async def test_duplicate_urls_fetched_once(self) -> None:
        # respx will raise if a mock is called more times than expected
        respx.get("http://start.com/").mock(return_value=httpx.Response(200, content=b""))
        mock_dupe = respx.get("http://dupe.com/").mock(
            return_value=httpx.Response(200, content=b"")
        )
        engine = Engine(concurrency=2, http2=False)
        await engine.run(_DupeTrpper("http://start.com/", "http://dupe.com/"))

        assert mock_dupe.call_count == 1

    @respx.mock
    async def test_fetch_error_does_not_crash_engine(self) -> None:
        respx.get("http://ok.com/").mock(return_value=httpx.Response(200, content=b""))
        respx.get("http://broken.com/").mock(side_effect=httpx.ConnectError("refused"))

        engine = Engine(concurrency=2, http2=False)
        # broken.com fetch fails — engine should still return items from ok.com
        items = await engine.run(
            _SimpleTrpper(["http://ok.com/", "http://broken.com/"])
        )
        assert len(items) == 1
        assert items[0].url == "http://ok.com/"  # type: ignore[union-attr]

    @respx.mock
    async def test_parse_exception_does_not_crash_engine(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))

        engine = Engine(concurrency=1, http2=False)
        # parse raises — engine should complete with no items (not crash)
        items = await engine.run(_RaisingTrpper(["http://example.com/"]))
        assert items == []

    @respx.mock
    async def test_custom_callback_routing(self) -> None:
        respx.get("http://list.com/").mock(return_value=httpx.Response(200, content=b""))
        respx.get("http://detail.com/").mock(return_value=httpx.Response(200, content=b""))

        engine = Engine(concurrency=2, http2=False)
        items = await engine.run(_CallbackTrpper("http://list.com/", "http://detail.com/"))

        assert len(items) == 1
        assert items[0].url == "http://detail.com/"  # type: ignore[union-attr]

    @respx.mock
    async def test_multiple_start_urls(self) -> None:
        for i in range(3):
            respx.get(f"http://page{i}.com/").mock(
                return_value=httpx.Response(200, content=b"")
            )

        engine = Engine(concurrency=3, http2=False)
        items = await engine.run(
            _SimpleTrpper([f"http://page{i}.com/" for i in range(3)])
        )
        assert len(items) == 3


class TestTrapperBase:
    def test_name_auto_derived_from_class(self) -> None:
        class MyFancyTrpper(Trapper):
            async def parse(self, response: Response):  # type: ignore[override]
                yield  # pragma: no cover

        assert MyFancyTrpper.name == "myfancytrpper"

    def test_explicit_name_not_overridden(self) -> None:
        class CustomNameTrpper(Trapper):
            name = "custom"

            async def parse(self, response: Response):  # type: ignore[override]
                yield  # pragma: no cover

        assert CustomNameTrpper.name == "custom"

    def test_start_requests_sets_trapper_meta(self) -> None:
        class SimpleTrpper(Trapper):
            start_urls = ["http://a.com", "http://b.com"]

            async def parse(self, response: Response):  # type: ignore[override]
                yield  # pragma: no cover

        reqs = SimpleTrpper().start_requests()
        assert len(reqs) == 2
        assert all(r.meta["trapper"] == "simpletrpper" for r in reqs)
