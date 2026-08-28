"""Tests for the REST API (chaser[api] extra)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from chaser.api.app import _manager, _parse_cors_origins, app
from chaser.api.manager import CrawlJob, CrawlManager, JobStatus
from chaser.engine.stats import CrawlStats
from chaser.item.base import Item

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_manager() -> None:
    """Reset the module-level manager between tests."""
    _manager._jobs.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(status: JobStatus = JobStatus.finished) -> CrawlJob:
    stats = CrawlStats()
    engine_mock = MagicMock()
    engine_mock.stats.snapshot.return_value = stats
    job = CrawlJob(id="abc12345", trapper_path="mymod:MyTrapper", _engine=engine_mock)
    job.status = status
    return job


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


def test_root_returns_service_name(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "chaser"


# ---------------------------------------------------------------------------
# CORS — CHASER_API_CORS_ORIGINS
# ---------------------------------------------------------------------------


def test_parse_cors_origins_empty_by_default() -> None:
    assert _parse_cors_origins("") == []


def test_parse_cors_origins_splits_and_strips() -> None:
    assert _parse_cors_origins("https://a.com, https://b.com ,,") == [
        "https://a.com",
        "https://b.com",
    ]


def test_cors_middleware_absent_by_default() -> None:
    # chaser.api.app is a long-lived singleton other tests already sent requests
    # through, so CORS can't be re-wired here via env var + reload without
    # re-running module-level side effects (e.g. Prometheus metric registration).
    # This only covers the default (unconfigured) state of that real app instance.
    from fastapi.middleware.cors import CORSMiddleware

    assert not any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_cors_middleware_sends_allow_origin_header_when_configured() -> None:
    """Same wiring app.py does when CHASER_API_CORS_ORIGINS is set, exercised on an
    isolated app instance to confirm it actually produces CORS response headers."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    probe = FastAPI()
    probe.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins("https://example.com"),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @probe.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    probe_client = TestClient(probe)

    allowed = probe_client.get("/ping", headers={"Origin": "https://example.com"})
    assert allowed.headers["access-control-allow-origin"] == "https://example.com"

    blocked = probe_client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


# ---------------------------------------------------------------------------
# GET /crawls — empty
# ---------------------------------------------------------------------------


def test_list_crawls_empty(client: TestClient) -> None:
    r = client.get("/crawls")
    assert r.status_code == 200
    assert r.json() == {"crawls": []}


# ---------------------------------------------------------------------------
# POST /crawls
# ---------------------------------------------------------------------------


def test_start_crawl_bad_trapper_path(client: TestClient) -> None:
    r = client.post("/crawls", json={"trapper": "no-colon"})
    assert r.status_code == 422


def test_start_crawl_missing_module(client: TestClient) -> None:
    r = client.post("/crawls", json={"trapper": "does.not.exist:Trapper"})
    assert r.status_code == 422


def test_start_crawl_creates_job(client: TestClient) -> None:
    with patch.object(CrawlManager, "start", new_callable=AsyncMock, return_value="deadbeef"):
        r = client.post("/crawls", json={"trapper": "mymod:MyTrapper"})
    assert r.status_code == 201
    assert r.json() == {"id": "deadbeef"}


def test_start_crawl_passes_trapper_kwargs_and_hooks(client: TestClient) -> None:
    with patch.object(
        CrawlManager, "start", new_callable=AsyncMock, return_value="deadbeef"
    ) as start_mock:
        r = client.post(
            "/crawls",
            json={
                "trapper": "mymod:MyTrapper",
                "trapper_kwargs": {"query": "iphone 17 pro"},
                "hooks": ["rate_limit", "robots"],
            },
        )
    assert r.status_code == 201
    _, kwargs = start_mock.call_args
    assert kwargs["trapper_kwargs"] == {"query": "iphone 17 pro"}
    assert kwargs["hooks"] == ["rate_limit", "robots"]


def test_start_crawl_unknown_hook_returns_422(client: TestClient) -> None:
    with patch.object(
        CrawlManager, "start", new_callable=AsyncMock, side_effect=ValueError("unknown hook")
    ):
        r = client.post("/crawls", json={"trapper": "mymod:MyTrapper", "hooks": ["nope"]})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /crawls/{id}
# ---------------------------------------------------------------------------


def test_get_crawl_not_found(client: TestClient) -> None:
    r = client.get("/crawls/nope")
    assert r.status_code == 404


def test_get_crawl_returns_stats(client: TestClient) -> None:
    job = _make_job(JobStatus.finished)
    _manager._jobs[job.id] = job

    r = client.get(f"/crawls/{job.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == job.id
    assert data["status"] == "finished"
    assert data["trapper"] == "mymod:MyTrapper"
    assert "stats" in data
    assert data["meta"] == {}


def test_get_crawl_returns_meta_when_set(client: TestClient) -> None:
    job = _make_job(JobStatus.finished)
    job.meta = {"failed_sources": {"shopee": "not implemented yet"}}
    _manager._jobs[job.id] = job

    r = client.get(f"/crawls/{job.id}")
    assert r.status_code == 200
    assert r.json()["meta"] == {"failed_sources": {"shopee": "not implemented yet"}}


# ---------------------------------------------------------------------------
# DELETE /crawls/{id}
# ---------------------------------------------------------------------------


def test_cancel_not_found(client: TestClient) -> None:
    r = client.delete("/crawls/ghost")
    assert r.status_code == 404


def test_cancel_already_finished(client: TestClient) -> None:
    job = _make_job(JobStatus.finished)
    _manager._jobs[job.id] = job

    r = client.delete(f"/crawls/{job.id}")
    assert r.status_code == 409


def test_cancel_running_job(client: TestClient) -> None:
    job = _make_job(JobStatus.running)
    task_mock = MagicMock()
    task_mock.done.return_value = False
    job._task = task_mock
    _manager._jobs[job.id] = job

    r = client.delete(f"/crawls/{job.id}")
    assert r.status_code == 204
    task_mock.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# GET /crawls/{id}/items
# ---------------------------------------------------------------------------


def test_get_items_not_found(client: TestClient) -> None:
    r = client.get("/crawls/ghost/items")
    assert r.status_code == 404


def test_get_items_empty(client: TestClient) -> None:
    job = _make_job(JobStatus.finished)
    _manager._jobs[job.id] = job

    r = client.get(f"/crawls/{job.id}/items")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_get_items_paginated() -> None:
    class _Link(Item):
        url: str

    job = _make_job(JobStatus.finished)
    job.items = [_Link(url=f"https://example.com/{i}") for i in range(5)]
    _manager._jobs[job.id] = job

    client = TestClient(app)
    r = client.get(f"/crawls/{job.id}/items?limit=2&offset=1")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["url"] == "https://example.com/1"


# ---------------------------------------------------------------------------
# GET /crawls — populated
# ---------------------------------------------------------------------------


def test_list_crawls_includes_all_jobs(client: TestClient) -> None:
    for i in range(3):
        job = CrawlJob(id=f"job{i}", trapper_path="m:T")
        job.status = JobStatus.finished
        _manager._jobs[job.id] = job

    r = client.get("/crawls")
    assert r.status_code == 200
    assert len(r.json()["crawls"]) == 3
