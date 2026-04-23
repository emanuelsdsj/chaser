from __future__ import annotations

from collections.abc import Mapping


class Headers(dict[str, str]):
    """Case-insensitive HTTP headers container."""

    def __init__(self, data: Mapping[str, str] | None = None, **kwargs: str) -> None:
        super().__init__()
        if data:
            for k, v in data.items():
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return super().__contains__(key.lower())
        return False

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        return super().get(key.lower(), default)

    def __repr__(self) -> str:
        return f"Headers({dict(self)!r})"
