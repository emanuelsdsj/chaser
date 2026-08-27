"""Tests for CrawlManager: trapper_kwargs, hooks, dedup_window, meta."""

from __future__ import annotations

import asyncio

import pytest

from chaser.api.manager import CrawlManager, JobStatus
from chaser.net.response import Response
from chaser.trapper.base import Trapper


class _EchoTrpper(Trapper):
    """No network calls (empty start_urls) — just echoes constructor args via meta."""

    name = "echo"

    def __init__(self, tag: str = "default") -> None:
        self.tag = tag
        self.start_urls = []

    async def parse(self, response: Response):  # type: ignore[override]
        yield  # pragma: no cover

    def get_meta(self) -> dict[str, str]:
        return {"tag": self.tag}


_ECHO_PATH = "tests.test_api.test_manager:_EchoTrpper"


async def _await_job(manager: CrawlManager, job_id: str) -> None:
    job = manager.get(job_id)
    assert job is not None
    assert job._task is not None
    await job._task


# ---------------------------------------------------------------------------
# trapper_kwargs
# ---------------------------------------------------------------------------


class TestTrapperKwargs:
    async def test_kwargs_passed_to_constructor(self) -> None:
        manager = CrawlManager()
        job_id = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "hello"})
        await _await_job(manager, job_id)

        job = manager.get(job_id)
        assert job is not None
        assert job.status == JobStatus.finished
        assert job.meta == {"tag": "hello"}

    async def test_no_kwargs_uses_defaults(self) -> None:
        manager = CrawlManager()
        job_id = await manager.start(_ECHO_PATH, {})
        await _await_job(manager, job_id)

        job = manager.get(job_id)
        assert job is not None
        assert job.meta == {"tag": "default"}

    async def test_unexpected_kwarg_raises_type_error(self) -> None:
        manager = CrawlManager()
        with pytest.raises(TypeError):
            await manager.start(_ECHO_PATH, {}, trapper_kwargs={"nope": "x"})


# ---------------------------------------------------------------------------
# hooks
# ---------------------------------------------------------------------------


class TestHooks:
    def test_resolve_hooks_returns_instances(self) -> None:
        manager = CrawlManager()
        resolved = manager._resolve_hooks(["rate_limit", "robots", "cookies"])
        assert len(resolved) == 3

    def test_resolve_unknown_hook_raises_value_error(self) -> None:
        manager = CrawlManager()
        with pytest.raises(ValueError):
            manager._resolve_hooks(["not_a_real_hook"])

    async def test_start_with_unknown_hook_raises_value_error(self) -> None:
        manager = CrawlManager()
        with pytest.raises(ValueError):
            await manager.start(_ECHO_PATH, {}, hooks=["not_a_real_hook"])

    async def test_start_with_known_hooks_runs_successfully(self) -> None:
        manager = CrawlManager()
        job_id = await manager.start(_ECHO_PATH, {}, hooks=["rate_limit", "robots"])
        await _await_job(manager, job_id)

        job = manager.get(job_id)
        assert job is not None
        assert job.status == JobStatus.finished


# ---------------------------------------------------------------------------
# dedup_window
# ---------------------------------------------------------------------------


class TestDedupWindow:
    async def test_disabled_by_default_creates_distinct_jobs(self) -> None:
        manager = CrawlManager()
        id1 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        id2 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        assert id1 != id2
        await _await_job(manager, id1)
        await _await_job(manager, id2)

    async def test_same_key_within_window_reuses_job(self) -> None:
        manager = CrawlManager(dedup_window=60.0)
        id1 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        id2 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        assert id1 == id2
        await _await_job(manager, id1)

    async def test_different_kwargs_not_deduped(self) -> None:
        manager = CrawlManager(dedup_window=60.0)
        id1 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        id2 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "b"})
        assert id1 != id2
        await _await_job(manager, id1)
        await _await_job(manager, id2)

    async def test_finished_job_outside_window_not_reused(self) -> None:
        manager = CrawlManager(dedup_window=0.01)
        id1 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        await _await_job(manager, id1)
        await asyncio.sleep(0.02)
        id2 = await manager.start(_ECHO_PATH, {}, trapper_kwargs={"tag": "a"})
        assert id1 != id2
        await _await_job(manager, id2)
