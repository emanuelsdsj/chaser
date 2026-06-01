"""Tests for ChaserMetrics — Prometheus collector."""

from __future__ import annotations

import prometheus_client as prom
import pytest

from chaser.metrics.collector import ChaserMetrics


@pytest.fixture
def registry() -> prom.CollectorRegistry:
    return prom.CollectorRegistry()


@pytest.fixture
def metrics(registry: prom.CollectorRegistry) -> ChaserMetrics:
    return ChaserMetrics(registry=registry)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sample_value(registry: prom.CollectorRegistry, sample_name: str, labels: dict) -> float:
    """Find a sample by sample.name (prom strips _total from Counter metric.name)."""
    for metric in registry.collect():
        for sample in metric.samples:
            if sample.name == sample_name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


_get_counter = _sample_value
_get_gauge = _sample_value


def _histogram_count(registry: prom.CollectorRegistry, name: str, labels: dict) -> float:
    return _sample_value(registry, name + "_count", labels)


# ---------------------------------------------------------------------------
# counter tests
# ---------------------------------------------------------------------------


def test_record_request_ok(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.record_request("job1", "ok")
    metrics.record_request("job1", "ok")
    assert _get_counter(registry, "chaser_requests_total", {"job": "job1", "result": "ok"}) == 2.0


def test_record_request_different_results(
    metrics: ChaserMetrics, registry: prom.CollectorRegistry
) -> None:
    metrics.record_request("crawl", "ok")
    metrics.record_request("crawl", "timeout")
    metrics.record_request("crawl", "failed")
    assert _get_counter(registry, "chaser_requests_total", {"job": "crawl", "result": "ok"}) == 1.0
    assert (
        _get_counter(registry, "chaser_requests_total", {"job": "crawl", "result": "timeout"})
        == 1.0
    )
    assert (
        _get_counter(registry, "chaser_requests_total", {"job": "crawl", "result": "failed"}) == 1.0
    )


def test_record_request_per_job_isolation(
    metrics: ChaserMetrics, registry: prom.CollectorRegistry
) -> None:
    metrics.record_request("job_a", "ok")
    metrics.record_request("job_b", "ok")
    assert _get_counter(registry, "chaser_requests_total", {"job": "job_a", "result": "ok"}) == 1.0
    assert _get_counter(registry, "chaser_requests_total", {"job": "job_b", "result": "ok"}) == 1.0


def test_record_item(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.record_item("myjob")
    metrics.record_item("myjob")
    metrics.record_item("myjob")
    assert _get_counter(registry, "chaser_items_scraped_total", {"job": "myjob"}) == 3.0


def test_record_bytes(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.record_bytes("job1", 1024)
    metrics.record_bytes("job1", 512)
    assert _get_counter(registry, "chaser_bytes_downloaded_total", {"job": "job1"}) == 1536.0


def test_record_http_error(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.record_http_error("job1", 404)
    metrics.record_http_error("job1", 404)
    metrics.record_http_error("job1", 429)
    assert (
        _get_counter(registry, "chaser_http_errors_total", {"job": "job1", "status_code": "404"})
        == 2.0
    )
    assert (
        _get_counter(registry, "chaser_http_errors_total", {"job": "job1", "status_code": "429"})
        == 1.0
    )


# ---------------------------------------------------------------------------
# histogram tests
# ---------------------------------------------------------------------------


def test_observe_latency_increments_count(
    metrics: ChaserMetrics, registry: prom.CollectorRegistry
) -> None:
    metrics.observe_latency("job1", 0.3)
    metrics.observe_latency("job1", 1.2)
    assert _histogram_count(registry, "chaser_request_duration_seconds", {"job": "job1"}) == 2.0


def test_observe_latency_sum(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.observe_latency("job1", 0.5)
    metrics.observe_latency("job1", 0.5)
    for metric in registry.collect():
        if metric.name == "chaser_request_duration_seconds":
            for sample in metric.samples:
                if sample.name.endswith("_sum") and sample.labels.get("job") == "job1":
                    assert abs(sample.value - 1.0) < 1e-9
                    return
    pytest.fail("sum sample not found")


# ---------------------------------------------------------------------------
# gauge tests
# ---------------------------------------------------------------------------


def test_set_queue_size(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.set_queue_size("job1", 42)
    assert _get_gauge(registry, "chaser_frontier_queue_size", {"job": "job1"}) == 42.0
    metrics.set_queue_size("job1", 10)
    assert _get_gauge(registry, "chaser_frontier_queue_size", {"job": "job1"}) == 10.0


def test_set_seen_urls(metrics: ChaserMetrics, registry: prom.CollectorRegistry) -> None:
    metrics.set_seen_urls("job1", 999)
    assert _get_gauge(registry, "chaser_frontier_seen_urls_total", {"job": "job1"}) == 999.0


# ---------------------------------------------------------------------------
# ASGI app
# ---------------------------------------------------------------------------


def test_make_asgi_app_returns_callable(metrics: ChaserMetrics) -> None:
    asgi_app = metrics.make_asgi_app()
    assert callable(asgi_app)


# ---------------------------------------------------------------------------
# import guard
# ---------------------------------------------------------------------------


def test_import_error_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "prometheus_client", None)  # type: ignore[arg-type]
    with pytest.raises(ImportError, match="prometheus-client"):
        ChaserMetrics()
