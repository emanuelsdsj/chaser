from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from chaser import __version__
from chaser.api.manager import CrawlManager, JobStatus

app = FastAPI(
    title="Chaser API",
    version=__version__,
    description="REST interface for managing and monitoring Chaser crawl jobs.",
)

_manager = CrawlManager()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    trapper: str
    concurrency: int = 16
    http2: bool = True
    timeout: float = 30.0
    proxy: str | None = None
    cache_dir: str | None = None
    frontier_db: str | None = None


class StatsPayload(BaseModel):
    requests_sent: int
    requests_ok: int
    requests_failed: int
    cache_hits: int
    items_scraped: int
    bytes_downloaded: int
    timeouts: int
    errors_by_status: dict[int, int]
    elapsed: float
    requests_per_second: float


class CrawlResponse(BaseModel):
    id: str
    status: str
    trapper: str
    stats: StatsPayload
    items_count: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_crawl_response(job: Any) -> CrawlResponse:
    s = job.stats
    return CrawlResponse(
        id=job.id,
        status=job.status.value,
        trapper=job.trapper_path,
        stats=StatsPayload(
            requests_sent=s.requests_sent,
            requests_ok=s.requests_ok,
            requests_failed=s.requests_failed,
            cache_hits=s.cache_hits,
            items_scraped=s.items_scraped,
            bytes_downloaded=s.bytes_downloaded,
            timeouts=s.timeouts,
            errors_by_status=s.errors_by_status,
            elapsed=s.elapsed,
            requests_per_second=s.requests_per_second,
        ),
        items_count=len(job.items),
        error=job.error,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "chaser", "version": __version__}


@app.post("/crawls", status_code=201)
async def start_crawl(body: StartRequest) -> dict[str, str]:
    """Start a crawl job in the background and return its ID."""
    engine_kwargs: dict[str, Any] = {
        "concurrency": body.concurrency,
        "http2": body.http2,
        "timeout": body.timeout,
    }
    if body.proxy is not None:
        engine_kwargs["proxy"] = body.proxy
    if body.cache_dir is not None:
        engine_kwargs["cache_dir"] = body.cache_dir
    if body.frontier_db is not None:
        engine_kwargs["frontier_db"] = body.frontier_db

    try:
        job_id = await _manager.start(body.trapper, engine_kwargs)
    except (ImportError, AttributeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"id": job_id}


@app.get("/crawls")
async def list_crawls() -> dict[str, list[CrawlResponse]]:
    """List all crawl jobs with their current status and stats."""
    return {"crawls": [_build_crawl_response(j) for j in _manager.list_jobs()]}


@app.get("/crawls/{crawl_id}")
async def get_crawl(crawl_id: str) -> CrawlResponse:
    """Get status and stats for a specific crawl job."""
    job = _manager.get(crawl_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl not found")
    return _build_crawl_response(job)


@app.delete("/crawls/{crawl_id}", status_code=204)
async def cancel_crawl(crawl_id: str) -> None:
    """Cancel a running crawl job."""
    job = _manager.get(crawl_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl not found")
    if job.status not in (JobStatus.pending, JobStatus.running):
        raise HTTPException(status_code=409, detail=f"crawl is already {job.status.value}")
    _manager.cancel(crawl_id)


@app.get("/crawls/{crawl_id}/items")
async def get_items(crawl_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Get items collected by a crawl job (paginated)."""
    job = _manager.get(crawl_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl not found")
    page = job.items[offset : offset + limit]
    return {
        "total": len(job.items),
        "offset": offset,
        "limit": limit,
        "items": [i.model_dump() for i in page],
    }
