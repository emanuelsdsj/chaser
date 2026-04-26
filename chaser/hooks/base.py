from __future__ import annotations

from chaser.net.request import Request
from chaser.net.response import Response


class RequestAborted(Exception):
    """Raised by a hook to cleanly skip a request.

    Unlike FetchError (network failure), this signals a deliberate decision
    not to fetch — robots.txt check, URL filter, auth guard, etc.
    The engine logs at DEBUG level and moves on to the next URL.
    """


class FetchHook:
    """Base class for request/response lifecycle hooks.

    Override only the methods you need — both are pass-through by default.
    Hooks run in registration order on every fetch performed by NetClient.

    Raise ``RequestAborted`` in ``before_request`` to skip the URL cleanly.
    Any other exception propagates as a fetch-level error.
    """

    async def before_request(self, request: Request) -> Request:
        return request

    async def after_response(self, response: Response) -> Response:
        return response
