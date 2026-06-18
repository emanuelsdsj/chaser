from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping


class Headers(MutableMapping[str, str]):
    """Case-insensitive HTTP headers container with multi-value support.

    Single-value access returns the last value set for that key.
    Use ``getlist()`` to retrieve all values (e.g. multiple Set-Cookie).
    ``headers[key] = value`` replaces all existing values; ``add()`` appends.
    """

    def __init__(
        self,
        data: Mapping[str, str | list[str]] | None = None,
        **kwargs: str,
    ) -> None:
        self._data: dict[str, list[str]] = {}
        if data:
            for k, v in data.items():
                if isinstance(v, list):
                    self._data[k.lower()] = list(v)
                else:
                    self._data[k.lower()] = [v]
        for k, v in kwargs.items():
            self._data[k.lower()] = [v]

    def __setitem__(self, key: str, value: str) -> None:
        self._data[key.lower()] = [value]

    def __getitem__(self, key: str) -> str:
        return self._data[key.lower()][-1]

    def __delitem__(self, key: str) -> None:
        del self._data[key.lower()]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return key.lower() in self._data
        return False

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        values = self._data.get(key.lower())
        return values[-1] if values is not None else default

    def getlist(self, key: str) -> list[str]:
        """Return all values for *key*. Empty list if the header is absent."""
        return list(self._data.get(key.lower(), []))

    def add(self, key: str, value: str) -> None:
        """Append *value* without replacing existing values for *key*."""
        self._data.setdefault(key.lower(), []).append(value)

    def to_dict_list(self) -> dict[str, list[str]]:
        """Serialise to ``dict[str, list[str]]``, preserving all values."""
        return {k: list(vs) for k, vs in self._data.items()}

    def __repr__(self) -> str:
        return f"Headers({dict(self)!r})"
