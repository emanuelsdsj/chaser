from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

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
            self.headers = Headers(self.headers)  # type: ignore[arg-type]

    def copy(self, **overrides: Any) -> Request:
        return dataclasses.replace(self, **overrides)

    def __repr__(self) -> str:
        return f"<Request [{self.method}] {self.url}>"

    # Priority queue requires comparison — higher int = higher priority (min-heap inverted)
    def __lt__(self, other: Request) -> bool:
        return self.priority > other.priority
