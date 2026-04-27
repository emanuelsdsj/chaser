from __future__ import annotations

from chaser.item.base import Item
from chaser.pipeline.base import Pipeline, Stage


class _TextItem(Item):
    value: str


class _DoubleStage(Stage):
    """Appends '-doubled' to the value."""

    async def process(self, item: Item) -> Item:
        assert isinstance(item, _TextItem)
        return _TextItem(value=item.value + "-doubled")


class _UpperStage(Stage):
    """Uppercases the value."""

    async def process(self, item: Item) -> Item:
        assert isinstance(item, _TextItem)
        return _TextItem(value=item.value.upper())


class _DropStage(Stage):
    """Always drops the item."""

    async def process(self, item: Item) -> Item | None:
        return None


class _RaisingStage(Stage):
    """Always raises."""

    async def process(self, item: Item) -> Item:
        raise RuntimeError("intentional stage failure")


class _RecordingStage(Stage):
    """Records open/close calls for lifecycle testing."""

    def __init__(self) -> None:
        self.opened = False
        self.closed = False
        self.received: list[Item] = []

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def process(self, item: Item) -> Item:
        self.received.append(item)
        return item


# ---------------------------------------------------------------------------
# Stage base
# ---------------------------------------------------------------------------


class TestStageBase:
    async def test_default_passthrough(self) -> None:
        stage = Stage()
        item = _TextItem(value="hello")
        result = await stage.process(item)
        assert result is item

    async def test_open_close_are_noops(self) -> None:
        stage = Stage()
        await stage.open()
        await stage.close()


# ---------------------------------------------------------------------------
# Pipeline chain
# ---------------------------------------------------------------------------


class TestPipeline:
    async def test_empty_pipeline_passes_item_through(self) -> None:
        pipeline = Pipeline([])
        item = _TextItem(value="x")
        result = await pipeline.process(item)
        assert result is item

    async def test_single_stage_transforms_item(self) -> None:
        pipeline = Pipeline([_DoubleStage()])
        result = await pipeline.process(_TextItem(value="a"))
        assert isinstance(result, _TextItem)
        assert result.value == "a-doubled"

    async def test_stages_run_in_order(self) -> None:
        pipeline = Pipeline([_DoubleStage(), _UpperStage()])
        result = await pipeline.process(_TextItem(value="hello"))
        assert isinstance(result, _TextItem)
        assert result.value == "HELLO-DOUBLED"

    async def test_drop_stage_returns_none(self) -> None:
        pipeline = Pipeline([_DropStage()])
        result = await pipeline.process(_TextItem(value="bye"))
        assert result is None

    async def test_stages_after_drop_are_skipped(self) -> None:
        recorder = _RecordingStage()
        pipeline = Pipeline([_DropStage(), recorder])
        result = await pipeline.process(_TextItem(value="x"))
        assert result is None
        assert len(recorder.received) == 0

    async def test_exception_in_stage_drops_item(self) -> None:
        recorder = _RecordingStage()
        pipeline = Pipeline([_RaisingStage(), recorder])
        result = await pipeline.process(_TextItem(value="x"))
        assert result is None
        assert len(recorder.received) == 0

    async def test_open_calls_all_stages(self) -> None:
        stages = [_RecordingStage(), _RecordingStage()]
        pipeline = Pipeline(stages)
        await pipeline.open()
        assert all(s.opened for s in stages)

    async def test_close_calls_all_stages(self) -> None:
        stages = [_RecordingStage(), _RecordingStage()]
        pipeline = Pipeline(stages)
        await pipeline.close()
        assert all(s.closed for s in stages)

    async def test_close_on_error_continues_to_remaining_stages(self) -> None:
        class _FailClose(Stage):
            closed = False

            async def close(self) -> None:
                raise RuntimeError("close failed")

        last = _RecordingStage()
        pipeline = Pipeline([_FailClose(), last])
        await pipeline.close()  # should not propagate
        assert last.closed

    async def test_run_is_async_context_manager(self) -> None:
        recorder = _RecordingStage()
        pipeline = Pipeline([recorder])
        async with pipeline.run():
            assert recorder.opened
        assert recorder.closed

    async def test_multiple_items_processed_independently(self) -> None:
        recorder = _RecordingStage()
        pipeline = Pipeline([recorder])
        async with pipeline.run():
            for i in range(5):
                await pipeline.process(_TextItem(value=str(i)))
        assert len(recorder.received) == 5
