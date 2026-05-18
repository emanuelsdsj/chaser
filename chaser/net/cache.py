from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


@dataclass
class CacheLookup:
    """Outcome of a single cache lookup."""

    response: Response | None
    fresh: bool
    conditional_headers: dict[str, str]


class HttpCache:
    """Disk cache that respects Cache-Control, ETag, and Last-Modified.

    Storage layout::

        {cache_dir}/{key[:2]}/{key[2:]}.meta.json   ← expiry + validator metadata
        {cache_dir}/{key[:2]}/{key[2:]}.body         ← raw response bytes

    Only GET requests with status in {200, 203, 204, 206, 300, 301, 308} are stored.
    Responses with ``Cache-Control: no-store`` are never written to disk.
    Responses with ``Cache-Control: no-cache`` are stored but always revalidated.

    Usage::

        cache = HttpCache(".cache")
        lookup = cache.lookup(request)
        if lookup.fresh:
            return lookup.response  # skip the network entirely
        if lookup.conditional_headers:
            request = add_headers(request, lookup.conditional_headers)
            # on 304 → cache.touch(request); return lookup.response
    """

    _CACHEABLE = frozenset({200, 203, 204, 206, 300, 301, 308})
    _RE_MAX_AGE = re.compile(r"\bmax-age=(\d+)")
    _RE_NO_STORE = re.compile(r"\bno-store\b")
    _RE_NO_CACHE = re.compile(r"\bno-cache\b")

    def __init__(self, cache_dir: str | Path) -> None:
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def lookup(self, request: Request) -> CacheLookup:
        """Check the cache for *request*.

        Returns a fresh entry (no network needed), a stale entry with conditional
        headers for revalidation, or a miss with no response.
        """
        key = self._key(request)
        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return CacheLookup(response=None, fresh=False, conditional_headers={})

        try:
            meta: dict[str, Any] = json.loads(meta_path.read_text())
            body = self._body_path(key).read_bytes()
        except (OSError, json.JSONDecodeError, ValueError):
            return CacheLookup(response=None, fresh=False, conditional_headers={})

        response = Response(
            url=meta["url"],
            status=meta["status"],
            headers=Headers(meta["headers"]),
            body=body,
            encoding=meta.get("encoding", "utf-8"),
            elapsed=0.0,
            from_cache=True,
        )

        fresh = self._is_fresh(meta)
        cond: dict[str, str] = {}
        if not fresh:
            if meta.get("etag"):
                cond["if-none-match"] = meta["etag"]
            if meta.get("last_modified"):
                cond["if-modified-since"] = meta["last_modified"]

        return CacheLookup(response=response, fresh=fresh, conditional_headers=cond)

    def store(self, request: Request, response: Response) -> None:
        """Write *response* to disk if cacheable. Silent no-op otherwise."""
        if request.method != "GET":
            return
        if response.status not in self._CACHEABLE:
            return

        cc = response.headers.get("cache-control", "") or ""
        if self._RE_NO_STORE.search(cc):
            return

        etag = response.headers.get("etag", "") or ""
        last_modified = response.headers.get("last-modified", "") or ""
        expires_at = self._compute_expires(response)

        if expires_at is None and not etag and not last_modified:
            return  # no TTL, no validators — nothing useful to cache

        if self._RE_NO_CACHE.search(cc):
            expires_at = time.time()  # stored but immediately stale → always revalidate

        key = self._key(request)
        meta: dict[str, Any] = {
            "url": response.url,
            "method": request.method,
            "status": response.status,
            "headers": dict(response.headers),
            "encoding": response.encoding,
            "cached_at": time.time(),
            "expires_at": expires_at,
            "etag": etag,
            "last_modified": last_modified,
        }

        meta_path = self._meta_path(key)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta))
        self._body_path(key).write_bytes(response.body)

    def touch(self, request: Request) -> None:
        """Reset the entry's expiry after a 304 Not Modified response.

        The server confirmed the cached content is still valid — update the
        timestamp so the TTL window starts fresh.
        """
        key = self._key(request)
        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            return

        now = time.time()
        meta["cached_at"] = now
        cc = Headers(meta.get("headers", {})).get("cache-control", "") or ""
        m = self._RE_MAX_AGE.search(cc)
        if m:
            meta["expires_at"] = now + int(m.group(1))
        meta_path.write_text(json.dumps(meta))

    # ------------------------------------------------------------------

    def _is_fresh(self, meta: dict[str, Any]) -> bool:
        expires_at = meta.get("expires_at")
        if expires_at is None:
            return False
        return float(expires_at) > time.time()

    def _compute_expires(self, response: Response) -> float | None:
        cc = response.headers.get("cache-control", "") or ""
        m = self._RE_MAX_AGE.search(cc)
        if m:
            return time.time() + int(m.group(1))
        raw = (response.headers.get("expires", "") or "").strip()
        if raw and raw != "0":
            try:
                return parsedate_to_datetime(raw).timestamp()
            except Exception:
                pass
        return None

    def _key(self, request: Request) -> str:
        return hashlib.sha256(f"{request.method}:{request.url}".encode()).hexdigest()

    def _meta_path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key[2:]}.meta.json"

    def _body_path(self, key: str) -> Path:
        return self._root / key[:2] / f"{key[2:]}.body"
