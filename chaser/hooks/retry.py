from __future__ import annotations

import asyncio
import logging
import random

from chaser.net.client import FetchError

logger = logging.getLogger(__name__)


class RetryPolicy:
    """Exponential backoff with full jitter for transport-level failures.

    Only retries ``FetchError`` (connection errors, timeouts, etc.).
    HTTP 4xx/5xx responses are not retried — that's application logic.

    Delay formula: ``min(base_delay * 2^attempt, max_delay) * uniform(0.5, 1.5)``

    Args:
        max_retries: how many times to retry after the initial attempt
        base_delay: wait in seconds before attempt 1 (doubles each retry)
        max_delay: upper cap on computed wait before jitter is applied
        jitter: multiply delay by uniform(0.5, 1.5) to spread concurrent retries
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self._base = base_delay
        self._max = max_delay
        self._jitter = jitter

    def should_retry(self, attempt: int, exc: Exception) -> bool:
        return isinstance(exc, FetchError) and attempt < self.max_retries

    async def wait(self, attempt: int) -> None:
        delay = min(self._base * (2**attempt), self._max)
        if self._jitter:
            delay *= random.uniform(0.5, 1.5)
        logger.debug("Retry %d — sleeping %.3fs", attempt + 1, delay)
        await asyncio.sleep(delay)
