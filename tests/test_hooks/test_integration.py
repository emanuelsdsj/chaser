from __future__ import annotations

import httpx
import pytest
import respx

from chaser.engine.runner import Engine
from chaser.hooks.base import FetchHook, RequestAborted
from chaser.hooks.retry import RetryPolicy
from chaser.item.base import Item
from chaser.net.client import NetClient
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.trapper.base import Trapper


class _PageItem(Item):
    url: str


class _SimpleTrapper(Trapper):
    name = "simple"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        yield _PageItem(url=response.url)


class TestHookWiring:
    @respx.mock
    async def test_before_request_hook_receives_each_request(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        seen_urls: list[str] = []

        class _Tracker(FetchHook):
            async def before_request(self, request: Request) -> Request:
                seen_urls.append(request.url)
                return request

        async with NetClient(hooks=[_Tracker()], http2=False) as client:
            await client.fetch(Request("http://example.com/"))

        assert seen_urls == ["http://example.com/"]

    @respx.mock
    async def test_after_response_hook_receives_response(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b"hello"))
        statuses: list[int] = []

        class _Tracker(FetchHook):
            async def after_response(self, response: Response) -> Response:
                statuses.append(response.status)
                return response

        async with NetClient(hooks=[_Tracker()], http2=False) as client:
            await client.fetch(Request("http://example.com/"))

        assert statuses == [200]

    async def test_request_aborted_propagates_out_of_fetch(self) -> None:
        class _AbortAll(FetchHook):
            async def before_request(self, request: Request) -> Request:
                raise RequestAborted("blocked in test")

        async with NetClient(hooks=[_AbortAll()], http2=False) as client:
            with pytest.raises(RequestAborted):
                await client.fetch(Request("http://example.com/"))

    @respx.mock
    async def test_engine_skips_aborted_url_continues_others(self) -> None:
        respx.get("http://ok.com/").mock(return_value=httpx.Response(200, content=b""))

        class _BlockOne(FetchHook):
            async def before_request(self, request: Request) -> Request:
                if "blocked" in request.url:
                    raise RequestAborted("test block")
                return request

        engine = Engine(concurrency=1, http2=False, hooks=[_BlockOne()])
        items = await engine.run(_SimpleTrapper(["http://ok.com/", "http://blocked.com/"]))
        assert len(items) == 1
        assert items[0].url == "http://ok.com/"  # type: ignore[union-attr]


class TestRetryIntegration:
    @respx.mock
    async def test_engine_retries_on_transport_failure(self) -> None:
        attempts = [0]

        def fail_twice(request: httpx.Request) -> httpx.Response:
            attempts[0] += 1
            if attempts[0] < 3:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, content=b"ok")

        respx.get("http://flaky.com/").mock(side_effect=fail_twice)

        engine = Engine(
            concurrency=1,
            http2=False,
            retry=RetryPolicy(max_retries=3, base_delay=0.001, jitter=False),
        )
        items = await engine.run(_SimpleTrapper(["http://flaky.com/"]))
        assert len(items) == 1
        assert attempts[0] == 3

    @respx.mock
    async def test_engine_gives_up_after_max_retries(self) -> None:
        respx.get("http://down.com/").mock(side_effect=httpx.ConnectError("down"))

        engine = Engine(
            concurrency=1,
            http2=False,
            retry=RetryPolicy(max_retries=2, base_delay=0.001, jitter=False),
        )
        items = await engine.run(_SimpleTrapper(["http://down.com/"]))
        assert items == []
