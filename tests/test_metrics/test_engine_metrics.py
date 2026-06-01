"""Integration tests — ChaserMetrics wired into Engine."""

from __future__ import annotations

import httpx
import prometheus_client as prom
import respx

from chaser.engine.runner import Engine
from chaser.item.base import Item
from chaser.metrics.collector import ChaserMetrics
from chaser.net.response import Response
from chaser.trapper.base import Trapper

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fresh_metrics() -> ChaserMetrics:
    return ChaserMetrics(registry=prom.CollectorRegistry())


def _sample_value(registry: prom.CollectorRegistry, sample_name: str, **labels: str) -> float:
    """Find a sample by sample.name (prom strips _total from Counter metric.name)."""
    for metric in registry.collect():
        for sample in metric.samples:
            if sample.name == sample_name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def _histogram_count(registry: prom.CollectorRegistry, name: str, **labels: str) -> float:
    return _sample_value(registry, name + "_count", **labels)


# ---------------------------------------------------------------------------
# minimal trappers
# ---------------------------------------------------------------------------


class _ItemTrapper(Trapper):
    name = "item_trapper"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        class _Link(Item):
            url: str

        yield _Link(url=response.url)


class _SilentTrapper(Trapper):
    """Fetches URLs but yields nothing."""

    name = "silent"

    def __init__(self, urls: list[str]) -> None:
        self.start_urls = urls

    async def parse(self, response: Response):  # type: ignore[override]
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestEngineMetrics:
    @respx.mock
    async def test_ok_request_increments_counter(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b"x"))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j1")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        assert _sample_value(m._registry, "chaser_requests_total", job="j1", result="ok") == 1.0

    @respx.mock
    async def test_item_increments_counter(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j2")
        await engine.run(_ItemTrapper(["http://example.com/"]))

        assert _sample_value(m._registry, "chaser_items_scraped_total", job="j2") == 1.0

    @respx.mock
    async def test_bytes_counter(self) -> None:
        body = b"hello world"
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=body))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j3")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        assert _sample_value(m._registry, "chaser_bytes_downloaded_total", job="j3") == len(body)

    @respx.mock
    async def test_latency_histogram_populated(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j4")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        assert _histogram_count(m._registry, "chaser_request_duration_seconds", job="j4") == 1.0

    @respx.mock
    async def test_http_error_counter(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(404, content=b""))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j5")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        assert (
            _sample_value(m._registry, "chaser_http_errors_total", job="j5", status_code="404")
            == 1.0
        )

    @respx.mock
    async def test_frontier_gauges_updated(self) -> None:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j6")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        # After crawl completes queue should be empty, seen_urls = 1
        assert _sample_value(m._registry, "chaser_frontier_queue_size", job="j6") == 0.0
        assert _sample_value(m._registry, "chaser_frontier_seen_urls_total", job="j6") == 1.0

    @respx.mock
    async def test_no_metrics_engine_runs_fine(self) -> None:
        """Engine without metrics= should work exactly as before."""
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, content=b""))
        engine = Engine(concurrency=1, http2=False)
        items = await engine.run(_ItemTrapper(["http://example.com/"]))
        assert len(items) == 1

    @respx.mock
    async def test_timeout_result_label(self) -> None:
        respx.get("http://example.com/").mock(side_effect=httpx.ReadTimeout("timed out"))
        m = _fresh_metrics()
        engine = Engine(concurrency=1, http2=False, metrics=m, job_name="j7")
        await engine.run(_SilentTrapper(["http://example.com/"]))

        assert (
            _sample_value(m._registry, "chaser_requests_total", job="j7", result="timeout") == 1.0
        )
