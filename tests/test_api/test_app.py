"""Tests for the REST API (chaser[api] extra)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from chaser.api.app import _manager, app
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
