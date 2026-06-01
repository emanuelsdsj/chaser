from __future__ import annotations

from typing import Any

_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class ChaserMetrics:
    """Prometheus metrics for a Chaser crawl.

    All metrics carry a ``job`` label so multiple concurrent crawls can be
    tracked in the same Prometheus / Grafana stack without collision.

    Requires the ``chaser[metrics]`` extra::

        pip install 'chaser[metrics]'

    Usage::

        metrics = ChaserMetrics()
        engine = Engine(metrics=metrics, job_name="product_crawl")
        await engine.run(MyTrapper())

    Then scrape ``GET /metrics`` from the running API server, or mount
    ``metrics.make_asgi_app()`` on your own ASGI app.

    Exposed series
    --------------
    - ``chaser_requests_total{job, result}``
      result: ok / cached / timeout / failed / circuit_open / aborted
    - ``chaser_items_scraped_total{job}``            — items yielded by trappers
    - ``chaser_bytes_downloaded_total{job}``         — response body bytes (cache hits excluded)
    - ``chaser_http_errors_total{job, status_code}`` — 4xx / 5xx responses
    - ``chaser_request_duration_seconds{job}``       — latency histogram (successful requests)
    - ``chaser_frontier_queue_size{job}``            — URLs waiting in the frontier
    - ``chaser_frontier_seen_urls_total{job}``       — total distinct URLs deduped
    """

    def __init__(self, registry: Any = None) -> None:
        try:
            import prometheus_client as prom
        except ImportError:
            raise ImportError(
                "prometheus-client is not installed. Run: pip install 'chaser[metrics]'"
            ) from None

        self._prom = prom
        self._registry = registry if registry is not None else prom.REGISTRY

        self._requests = prom.Counter(
            "chaser_requests_total",
            "Total fetch attempts labelled by outcome",
            ["job", "result"],
            registry=self._registry,
        )
        self._items = prom.Counter(
            "chaser_items_scraped_total",
            "Items yielded by trappers",
            ["job"],
            registry=self._registry,
        )
        self._bytes = prom.Counter(
            "chaser_bytes_downloaded_total",
            "Response body bytes received (cache hits excluded)",
            ["job"],
            registry=self._registry,
        )
        self._http_errors = prom.Counter(
            "chaser_http_errors_total",
            "HTTP 4xx/5xx responses by status code",
            ["job", "status_code"],
            registry=self._registry,
        )
        self._latency = prom.Histogram(
            "chaser_request_duration_seconds",
            "Time from connection start to full response body (successful requests only)",
            ["job"],
            buckets=_LATENCY_BUCKETS,
            registry=self._registry,
        )
        self._queue_size = prom.Gauge(
            "chaser_frontier_queue_size",
            "URLs currently waiting in the frontier queue",
            ["job"],
            registry=self._registry,
        )
        self._seen_urls = prom.Gauge(
            "chaser_frontier_seen_urls_total",
            "Total distinct URLs that have passed through the frontier",
            ["job"],
            registry=self._registry,
        )

    # ------------------------------------------------------------------
    # recording methods called by Engine
    # ------------------------------------------------------------------

    def record_request(self, job: str, result: str) -> None:
        """Increment requests counter. result: ok|cached|timeout|failed|circuit_open|aborted"""
        self._requests.labels(job=job, result=result).inc()

    def observe_latency(self, job: str, duration: float) -> None:
        self._latency.labels(job=job).observe(duration)

    def record_item(self, job: str) -> None:
        self._items.labels(job=job).inc()

    def record_bytes(self, job: str, n: int) -> None:
        self._bytes.labels(job=job).inc(n)

    def record_http_error(self, job: str, status_code: int) -> None:
        self._http_errors.labels(job=job, status_code=str(status_code)).inc()

    def set_queue_size(self, job: str, n: int) -> None:
        self._queue_size.labels(job=job).set(n)

    def set_seen_urls(self, job: str, n: int) -> None:
        self._seen_urls.labels(job=job).set(n)

    # ------------------------------------------------------------------
    # ASGI endpoint
    # ------------------------------------------------------------------

    def make_asgi_app(self) -> Any:
        """Return a prometheus_client ASGI app to mount at /metrics."""
        return self._prom.make_asgi_app(registry=self._registry)
