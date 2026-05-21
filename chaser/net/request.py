from __future__ import annotations

import base64
import dataclasses
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from chaser.net.headers import Headers


@dataclass
class Request:
    url: str
    method: str = "GET"
    headers: Headers = field(default_factory=Headers)
    body: bytes | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    callback: str | None = None
    use_browser: bool = False

    def __post_init__(self) -> None:
        self.method = self.method.upper()
        if not isinstance(self.headers, Headers):
            self.headers = Headers(self.headers)

    @classmethod
    def from_form(
        cls,
        url: str,
        data: dict[str, str],
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Request:
        """Build a form POST request (application/x-www-form-urlencoded).

        Multipart/form-data is not supported yet — use ``body`` directly for that.
        """
        merged = {"content-type": "application/x-www-form-urlencoded"}
        merged.update(headers or {})
        return cls(
            url=url,
            method=method,
            body=urlencode(data).encode("utf-8"),
            headers=Headers(merged),
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict.

        ``meta`` values must be JSON-serialisable — this is only relevant
        when using ``Engine(frontier_db=...)`` for crawl resume.
        """
        return {
            "url": self.url,
            "method": self.method,
            "headers": dict(self.headers),
            "body": base64.b64encode(self.body).decode("ascii") if self.body is not None else None,
            "meta": self.meta,
            "priority": self.priority,
            "callback": self.callback,
            "use_browser": self.use_browser,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Request:
        body_b64: str | None = data.get("body")
        return cls(
            url=data["url"],
            method=data.get("method", "GET"),
            headers=Headers(data.get("headers") or {}),
            body=base64.b64decode(body_b64) if body_b64 is not None else None,
            meta=data.get("meta") or {},
            priority=data.get("priority", 0),
            callback=data.get("callback"),
            use_browser=data.get("use_browser", False),
        )

    def copy(self, **overrides: Any) -> Request:
        return dataclasses.replace(self, **overrides)

    def __repr__(self) -> str:
        return f"<Request [{self.method}] {self.url}>"

    # Priority queue requires comparison — higher int = higher priority (min-heap inverted)
    def __lt__(self, other: Request) -> bool:
        return self.priority > other.priority
