from __future__ import annotations

import asyncio
import importlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from chaser.engine.runner import Engine
from chaser.engine.stats import CrawlStats
from chaser.hooks import CookieJarHook, FetchHook, RateLimitHook, RobotsHook
from chaser.item.base import Item

if TYPE_CHECKING:
    from chaser.metrics.collector import ChaserMetrics


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    finished = "finished"
    cancelled = "cancelled"
    failed = "failed"


_HOOK_REGISTRY: dict[str, Callable[[], FetchHook]] = {
    "rate_limit": lambda: RateLimitHook(rate=1.0),
    "robots": lambda: RobotsHook(),
    "cookies": lambda: CookieJarHook(),
}


@dataclass
class CrawlJob:
    id: str
    trapper_path: str
    status: JobStatus = JobStatus.pending
    items: list[Item] = field(default_factory=list)
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    _engine: Engine | None = field(default=None, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def stats(self) -> CrawlStats:
        if self._engine is not None:
            return self._engine.stats.snapshot()
        return CrawlStats()


class CrawlManager:
    """Manages crawl jobs running as asyncio background tasks."""

    def __init__(self, metrics: ChaserMetrics | None = None, dedup_window: float = 0.0) -> None:
        self._jobs: dict[str, CrawlJob] = {}
        self._metrics = metrics
        self._dedup_window = dedup_window
        self._dedup_index: dict[str, str] = {}

    def _load_trapper(self, path: str) -> Any:
        """Import a Trapper class from 'module.path:ClassName' notation."""
        if ":" not in path:
            raise ValueError(f"expected 'module.path:ClassName', got {path!r}")
        module_path, cls_name = path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, cls_name, None)
        if cls is None:
            raise AttributeError(f"{cls_name!r} not found in {module_path!r}")
        return cls

    def _resolve_hooks(self, names: list[str]) -> list[FetchHook]:
        resolved = []
        for name in names:
            factory = _HOOK_REGISTRY.get(name)
            if factory is None:
                raise ValueError(f"unknown hook {name!r}, expected one of {sorted(_HOOK_REGISTRY)}")
            resolved.append(factory())
        return resolved

    def _dedup_key(self, trapper_path: str, trapper_kwargs: dict[str, Any] | None) -> str:
        return f"{trapper_path}|{json.dumps(trapper_kwargs or {}, sort_keys=True)}"

    def _reusable_job(self, key: str) -> str | None:
        job_id = self._dedup_index.get(key)
        if job_id is None:
            return None
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.status in (JobStatus.pending, JobStatus.running):
            return job_id
        if job.status == JobStatus.finished and (
            time.monotonic() - job.created_at < self._dedup_window
        ):
            return job_id
        return None

    async def start(
        self,
        trapper_path: str,
        engine_kwargs: dict[str, Any],
        trapper_kwargs: dict[str, Any] | None = None,
        hooks: list[str] | None = None,
    ) -> str:
        """Start a crawl job and return its ID."""
        dedup_key = None
        if self._dedup_window > 0:
            dedup_key = self._dedup_key(trapper_path, trapper_kwargs)
            reused = self._reusable_job(dedup_key)
            if reused is not None:
                return reused

        TrapperClass = self._load_trapper(trapper_path)
        trapper = TrapperClass(**(trapper_kwargs or {}))

        job_id = uuid.uuid4().hex[:8]

        kw = dict(engine_kwargs)
        if hooks:
            kw["hooks"] = self._resolve_hooks(hooks)
        if self._metrics is not None:
            kw["metrics"] = self._metrics
            kw["job_name"] = job_id
        engine = Engine(**kw)

        job = CrawlJob(id=job_id, trapper_path=trapper_path, _engine=engine)
        self._jobs[job_id] = job
        if dedup_key is not None:
            self._dedup_index[dedup_key] = job_id

        async def _run() -> None:
            job.status = JobStatus.running
            try:
                items = await engine.run(trapper)
                job.items = items
                job.meta = trapper.get_meta()
                job.status = JobStatus.finished
            except asyncio.CancelledError:
                job.status = JobStatus.cancelled
            except Exception as exc:
                job.error = str(exc)
                job.status = JobStatus.failed

        job._task = asyncio.create_task(_run())
        return job_id

    def get(self, job_id: str) -> CrawlJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[CrawlJob]:
        return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job._task is None or job._task.done():
            return False
        job._task.cancel()
        return True
