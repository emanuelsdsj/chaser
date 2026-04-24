from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chaser.net.response import Response
    from chaser.trapper.base import Trapper

logger = logging.getLogger(__name__)


async def execute(
    trapper: Trapper,
    response: Response,
    callback: str | None = None,
) -> AsyncIterator[Any]:
    """Call a trapper's parse method and yield results, catching all exceptions.

    Exceptions inside the parse method are logged and swallowed — the engine
    keeps running. This is the core isolation guarantee of the Trap Layer:
    a broken trapper never takes down the crawl.

    :param trapper: The trapper whose method will be called.
    :param response: The HTTP response to parse.
    :param callback: Method name to call. Defaults to ``"parse"``.
    """
    method_name = callback or "parse"
    method = getattr(trapper, method_name, None)

    if method is None:
        logger.error(
            "Trapper %r has no method %r — dropping response for %s",
            trapper.name,
            method_name,
            response.url,
        )
        return

    try:
        async for result in method(response):
            yield result
    except Exception:
        logger.exception(
            "Unhandled exception in %r.%s() while parsing %s",
            trapper.name,
            method_name,
            response.url,
        )
