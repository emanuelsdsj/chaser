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
    from_cache: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.headers, Headers):
            self.headers = Headers(self.headers)

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

    def follow(
        self,
        url: str,
        *,
        callback: str | None = None,
        meta: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Request:
        """Build a Request from *url* resolved relative to this response.

        Saves the urljoin + Request() boilerplate in parse methods.
        """
        from chaser.net.request import Request

        return Request(
            url=self.urljoin(url),
            callback=callback,
            meta=dict(meta) if meta else {},
            **kwargs,
        )

    def follow_all(
        self,
        css: str,
        *,
        callback: str | None = None,
        meta: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Request]:
        """Follow all URLs extracted by *css* selector (e.g. ``a::attr(href)``).

        Empty and whitespace-only values are skipped. Each URL is resolved
        relative to this response before building the Request.
        """
        return [
            self.follow(href, callback=callback, meta=dict(meta) if meta else {}, **kwargs)
            for href in self.selector.css(css).getall()
            if href.strip()
        ]

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
