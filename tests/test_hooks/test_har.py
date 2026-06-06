from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from chaser.hooks.har import HarWriter
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    url: str = "https://example.com/",
    status: int = 200,
    body: bytes = b"<html></html>",
    elapsed: float = 0.123,
    request: Request | None = None,
    headers: dict | None = None,
) -> Response:
    if request is None:
        request = Request(url=url)
    return Response(
        url=url,
        status=status,
        headers=Headers(headers or {"content-type": "text/html"}),
        body=body,
        encoding="utf-8",
        elapsed=elapsed,
        request=request,
    )


# ---------------------------------------------------------------------------
# after_response — captures entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_response_captures_entry() -> None:
    har = HarWriter("/dev/null")
    resp = _make_response()
    await har.after_response(resp)
    assert har.entry_count == 1


@pytest.mark.asyncio
async def test_after_response_returns_response_unchanged() -> None:
    har = HarWriter("/dev/null")
    resp = _make_response()
    result = await har.after_response(resp)
    assert result is resp


@pytest.mark.asyncio
async def test_multiple_responses_captured() -> None:
    har = HarWriter("/dev/null")
    for i in range(5):
        await har.after_response(_make_response(url=f"https://example.com/{i}"))
    assert har.entry_count == 5


# ---------------------------------------------------------------------------
# HAR entry structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_has_required_har_fields() -> None:
    har = HarWriter("/dev/null")
    resp = _make_response(url="https://example.com/page", status=200)
    await har.after_response(resp)

    entry = har._entries[0]
    assert "startedDateTime" in entry
    assert "time" in entry
    assert "request" in entry
    assert "response" in entry
    assert "cache" in entry
    assert "timings" in entry


@pytest.mark.asyncio
async def test_entry_request_fields() -> None:
    har = HarWriter("/dev/null")
    req = Request(url="https://example.com/search?q=test&page=1")
    resp = _make_response(url="https://example.com/search?q=test&page=1", request=req)
    await har.after_response(resp)

    req_entry = har._entries[0]["request"]
    assert req_entry["method"] == "GET"
    assert req_entry["url"] == "https://example.com/search?q=test&page=1"
    qs = {p["name"]: p["value"] for p in req_entry["queryString"]}
    assert qs["q"] == "test"
    assert qs["page"] == "1"


@pytest.mark.asyncio
async def test_entry_response_fields() -> None:
    har = HarWriter("/dev/null")
    resp = _make_response(
        status=404,
        body=b"not found",
        headers={"content-type": "text/plain"},
    )
    await har.after_response(resp)

    resp_entry = har._entries[0]["response"]
    assert resp_entry["status"] == 404
    assert resp_entry["bodySize"] == len(b"not found")
    assert resp_entry["content"]["mimeType"] == "text/plain"


@pytest.mark.asyncio
async def test_entry_timing_reflects_elapsed() -> None:
    har = HarWriter("/dev/null")
    resp = _make_response(elapsed=1.5)
    await har.after_response(resp)

    entry = har._entries[0]
    assert abs(entry["time"] - 1500.0) < 0.1
    assert abs(entry["timings"]["wait"] - 1500.0) < 0.1


@pytest.mark.asyncio
async def test_entry_post_request_body() -> None:
    har = HarWriter("/dev/null")
    req = Request.from_form(
        "https://example.com/login",
        data={"user": "alice", "pass": "secret"},
    )
    resp = _make_response(url="https://example.com/login", request=req)
    await har.after_response(resp)

    req_entry = har._entries[0]["request"]
    assert req_entry["method"] == "POST"
    assert req_entry["bodySize"] > 0
    assert "postData" in req_entry


@pytest.mark.asyncio
async def test_entry_without_request() -> None:
    """Responses without an attached request should still produce valid entries."""
    har = HarWriter("/dev/null")
    resp = Response(
        url="https://example.com/",
        status=200,
        headers=Headers({"content-type": "text/html"}),
        body=b"<html></html>",
        request=None,
    )
    await har.after_response(resp)

    entry = har._entries[0]
    assert entry["request"]["method"] == "GET"
    assert entry["request"]["url"] == "https://example.com/"


# ---------------------------------------------------------------------------
# flush() — writes HAR file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_writes_valid_json() -> None:
    with tempfile.NamedTemporaryFile(suffix=".har", delete=False) as f:
        path = Path(f.name)

    har = HarWriter(path)
    await har.after_response(_make_response())
    har.flush()

    data = json.loads(path.read_text())
    assert "log" in data
    assert data["log"]["version"] == "1.2"
    assert len(data["log"]["entries"]) == 1

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_flush_with_alternate_path() -> None:
    with tempfile.NamedTemporaryFile(suffix=".har", delete=False) as f:
        alt_path = Path(f.name)

    har = HarWriter("/dev/null")
    await har.after_response(_make_response())
    har.flush(alt_path)

    data = json.loads(alt_path.read_text())
    assert len(data["log"]["entries"]) == 1

    alt_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_flush_har_creator_info() -> None:
    with tempfile.NamedTemporaryFile(suffix=".har", delete=False) as f:
        path = Path(f.name)

    har = HarWriter(path)
    har.flush()

    data = json.loads(path.read_text())
    creator = data["log"]["creator"]
    assert creator["name"] == "chaser"
    assert "version" in creator

    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Context manager — auto-flush
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_flushes_on_exit() -> None:
    with tempfile.NamedTemporaryFile(suffix=".har", delete=False) as f:
        path = Path(f.name)

    async with HarWriter(path) as har:
        await har.after_response(_make_response(url="https://example.com/a"))
        await har.after_response(_make_response(url="https://example.com/b"))

    data = json.loads(path.read_text())
    assert len(data["log"]["entries"]) == 2

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_context_manager_returns_self() -> None:
    har = HarWriter("/dev/null")
    async with har as h:
        assert h is har


# ---------------------------------------------------------------------------
# Concurrency — lock prevents race on _entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_responses_all_captured() -> None:
    import asyncio

    har = HarWriter("/dev/null")
    responses = [_make_response(url=f"https://example.com/{i}") for i in range(20)]
    await asyncio.gather(*(har.after_response(r) for r in responses))
    assert har.entry_count == 20
