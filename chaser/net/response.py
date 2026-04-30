from __future__ import annotations

import json as _json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin as _urljoin

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

    def urljoin(self, url: str) -> str:
        """Resolve *url* relative to this response's URL."""
        return _urljoin(self.url, url)

    @property
    def selector(self) -> Selector:
        from chaser.extract.selector import Selector

        return Selector.from_response(self)

    @property
    def json_selector(self) -> Selector:
        """Selector for JSON responses — supports ``.jmespath()``."""
        from chaser.extract.selector import Selector

        return Selector(self.text, type="json")

    def __repr__(self) -> str:
        return f"<Response [{self.status}] {self.url}>"
