from __future__ import annotations

import asyncio
import importlib
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from chaser.engine.runner import Engine
from chaser.engine.stats import CrawlStats
from chaser.item.base import Item

if TYPE_CHECKING:
    from chaser.metrics.collector import ChaserMetrics


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    finished = "finished"
    cancelled = "cancelled"
    failed = "failed"


@dataclass
class CrawlJob:
    id: str
    trapper_path: str
    status: JobStatus = JobStatus.pending
    items: list[Item] = field(default_factory=list)
    error: str | None = None
    _engine: Engine | None = field(default=None, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    @property
    def stats(self) -> CrawlStats:
        if self._engine is not None:
            return self._engine.stats.snapshot()
        return CrawlStats()


class CrawlManager:
    """Manages crawl jobs running as asyncio background tasks."""

    def __init__(self, metrics: ChaserMetrics | None = None) -> None:
        self._jobs: dict[str, CrawlJob] = {}
        self._metrics = metrics

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

    async def start(self, trapper_path: str, engine_kwargs: dict[str, Any]) -> str:
        """Start a crawl job and return its ID."""
        TrapperClass = self._load_trapper(trapper_path)
        trapper = TrapperClass()

        job_id = uuid.uuid4().hex[:8]

        kw = dict(engine_kwargs)
        if self._metrics is not None:
            kw["metrics"] = self._metrics
            kw["job_name"] = job_id
        engine = Engine(**kw)

        job = CrawlJob(id=job_id, trapper_path=trapper_path, _engine=engine)
        self._jobs[job_id] = job

        async def _run() -> None:
            job.status = JobStatus.running
            try:
                items = await engine.run(trapper)
                job.items = items
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
