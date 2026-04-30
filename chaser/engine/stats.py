from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CrawlStats:
    """Counters collected during a crawl run.

    Populated by the Engine as it processes requests and items.
    Available on ``engine.stats`` after ``engine.run()`` completes.

    Example::

        engine = Engine()
        await engine.run(MyTrapper())
        print(engine.stats)
        # CrawlStats(requests_sent=42, items_scraped=38, ...)
    """

    requests_sent: int = 0
    requests_ok: int = 0
    requests_failed: int = 0
    items_scraped: int = 0
    bytes_downloaded: int = 0
    _start: float = field(default_factory=time.monotonic, repr=False)
    _finish: float | None = field(default=None, repr=False)

    def _mark_finished(self) -> None:
        self._finish = time.monotonic()

    @property
    def elapsed(self) -> float:
        """Seconds from crawl start to finish (or now if still running)."""
        return (self._finish or time.monotonic()) - self._start

    @property
    def requests_per_second(self) -> float:
        d = self.elapsed
        return self.requests_sent / d if d > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"CrawlStats("
            f"requests_sent={self.requests_sent}, "
            f"requests_ok={self.requests_ok}, "
            f"requests_failed={self.requests_failed}, "
            f"items_scraped={self.items_scraped}, "
            f"bytes_downloaded={self.bytes_downloaded}, "
            f"elapsed={self.elapsed:.2f}s)"
        )
