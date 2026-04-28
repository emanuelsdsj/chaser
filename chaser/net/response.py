from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chaser.net.headers import Headers

if TYPE_CHECKING:
    from chaser.extract.selector import Selector
    from chaser.net.request import Request


@dataclass
class Response:
    url: str
    status: int
    headers: Headers
    body: bytes
    encoding: str = "utf-8"
    elapsed: float = 0.0
    request: Request | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.headers, Headers):
            self.headers = Headers(self.headers)  # type: ignore[arg-type]

    @property
    def text(self) -> str:
        return self.body.decode(self.encoding, errors="replace")

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self, **kwargs: Any) -> Any:
        return _json.loads(self.body, **kwargs)

    @property
    def selector(self) -> Selector:
        from chaser.extract.selector import Selector

        return Selector.from_response(self)

    def __repr__(self) -> str:
        return f"<Response [{self.status}] {self.url}>"
