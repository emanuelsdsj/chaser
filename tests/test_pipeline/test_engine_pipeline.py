from __future__ import annotations

import httpx
import respx

from chaser.engine.runner import Engine
from chaser.item.base import Item
from chaser.net.response import Response
from chaser.pipeline.base import Pipeline, Stage
from chaser.trapper.base import Trapper


class _PageItem(Item):
    url: str
    status: int


class _SimpleTrpper(Trapper):
    name = "simple_pl"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        yield _PageItem(url=response.url, status=response.status)


class _CollectStage(Stage):
    """Collects every item it receives for assertion in tests."""

    def __init__(self) -> None:
        self.received: list[Item] = []

    async def process(self, item: Item) -> Item:
        self.received.append(item)
        return item


class _DropAllStage(Stage):
    async def process(self, item: Item) -> Item | None:
        return None


class TestEnginePipelineIntegration:
    @respx.mock
    async def test_items_routed_through_pipeline(self) -> None:
        respx.get("http://p1.com/").mock(return_value=httpx.Response(200, content=b""))

        collector = _CollectStage()
        engine = Engine(concurrency=1, http2=False, pipeline=Pipeline([collector]))
        returned = await engine.run(_SimpleTrpper(["http://p1.com/"]))

        # pipeline consumed items — in-memory list is empty
        assert returned == []
        # but collector got the item
        assert len(collector.received) == 1
        assert isinstance(collector.received[0], _PageItem)

    @respx.mock
    async def test_without_pipeline_returns_items(self) -> None:
        respx.get("http://p2.com/").mock(return_value=httpx.Response(200, content=b""))

        engine = Engine(concurrency=1, http2=False)
        returned = await engine.run(_SimpleTrpper(["http://p2.com/"]))

        assert len(returned) == 1
        assert isinstance(returned[0], _PageItem)

    @respx.mock
    async def test_pipeline_receives_all_items(self) -> None:
        for i in range(4):
            respx.get(f"http://pg{i}.com/").mock(return_value=httpx.Response(200, content=b""))

        collector = _CollectStage()
        engine = Engine(
            concurrency=4,
            http2=False,
            pipeline=Pipeline([collector]),
        )
        await engine.run(_SimpleTrpper([f"http://pg{i}.com/" for i in range(4)]))

        assert len(collector.received) == 4

    @respx.mock
    async def test_drop_stage_prevents_later_stages(self) -> None:
        respx.get("http://drop.com/").mock(return_value=httpx.Response(200, content=b""))

        after_drop = _CollectStage()
        engine = Engine(
            concurrency=1,
            http2=False,
            pipeline=Pipeline([_DropAllStage(), after_drop]),
        )
        await engine.run(_SimpleTrpper(["http://drop.com/"]))

        assert len(after_drop.received) == 0

    @respx.mock
    async def test_pipeline_lifecycle_open_close(self) -> None:
        respx.get("http://lc.com/").mock(return_value=httpx.Response(200, content=b""))

        class _LifecycleStage(Stage):
            opened = False
            closed = False

            async def open(self) -> None:
                self.opened = True

            async def close(self) -> None:
                self.closed = True

            async def process(self, item: Item) -> Item:
                return item

        stage = _LifecycleStage()
        engine = Engine(concurrency=1, http2=False, pipeline=Pipeline([stage]))
        await engine.run(_SimpleTrpper(["http://lc.com/"]))

        assert stage.opened
        assert stage.closed
