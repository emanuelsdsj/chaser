from __future__ import annotations

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

    def copy(self, **overrides: Any) -> Request:
        return dataclasses.replace(self, **overrides)

    def __repr__(self) -> str:
        return f"<Request [{self.method}] {self.url}>"

    # Priority queue requires comparison — higher int = higher priority (min-heap inverted)
    def __lt__(self, other: Request) -> bool:
        return self.priority > other.priority
