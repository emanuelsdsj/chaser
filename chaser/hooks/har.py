from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlsplit

from chaser.hooks.base import FetchHook

if TYPE_CHECKING:
    from chaser.net.response import Response

_CHASER_VERSION = "0.3.0"


class HarWriter(FetchHook):
    """Records HTTP traffic to a HAR 1.2 file for replay and debugging.

    Captures every request/response pair that passes through NetClient.
    Call flush() when the crawl is done to write the accumulated entries,
    or use as an async context manager to auto-flush on exit.

    Each entry includes the full request (method, URL, headers, body) and
    response (status, headers, content size, timing) in standard HAR format,
    making it easy to replay traffic in browser devtools or Insomnia.

    Usage::

        har = HarWriter("crawl.har")
        engine = Engine(hooks=[har])
        await engine.run(MyTrapper())
        har.flush()

    Or let it flush automatically::

        async with HarWriter("crawl.har") as har:
            engine = Engine(hooks=[har])
            await engine.run(MyTrapper())
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._entries: list[dict[str, object]] = []
        self._lock = asyncio.Lock()

    async def after_response(self, response: Response) -> Response:
        entry = self._build_entry(response)
        async with self._lock:
            self._entries.append(entry)
        return response

    def flush(self, path: str | Path | None = None) -> None:
        """Write accumulated entries to disk in HAR 1.2 format.

        Pass *path* to override the destination set at construction time.
        Safe to call multiple times — each call overwrites the file.
        """
        target = Path(path) if path else self._path
        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "chaser", "version": _CHASER_VERSION, "comment": ""},
                "entries": self._entries,
            }
        }
        target.write_text(json.dumps(har, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    async def __aenter__(self) -> HarWriter:
        return self

    async def __aexit__(self, *_: object) -> None:
        self.flush()

    def _build_entry(self, response: Response) -> dict[str, object]:
        req = response.request
        started = datetime.now(tz=UTC).isoformat()
        elapsed_ms = response.elapsed * 1000

        if req is not None:
            parts = urlsplit(req.url)
            query_string = [{"name": k, "value": v} for k, v in parse_qsl(parts.query)]
            req_headers = [{"name": k, "value": v} for k, v in req.headers.items()]
            method = req.method
            url = req.url
            body_size = len(req.body) if req.body else 0
            post_data: dict[str, str] | None = None
            if req.body:
                mime = dict(req.headers).get("content-type", "application/octet-stream")
                post_data = {
                    "mimeType": mime,
                    "text": req.body.decode("utf-8", errors="replace"),
                }
        else:
            query_string = []
            req_headers = []
            method = "GET"
            url = response.url
            body_size = 0
            post_data = None

        request_entry: dict[str, object] = {
            "method": method,
            "url": url,
            "httpVersion": "HTTP/1.1",
            "headers": req_headers,
            "queryString": query_string,
            "cookies": [],
            "headersSize": -1,
            "bodySize": body_size,
        }
        if post_data is not None:
            request_entry["postData"] = post_data

        mime_type = response.headers.get("content-type", "application/octet-stream")
        response_size = len(response.body)

        return {
            "startedDateTime": started,
            "time": elapsed_ms,
            "request": request_entry,
            "response": {
                "status": response.status,
                "statusText": "",
                "httpVersion": "HTTP/1.1",
                "headers": [{"name": k, "value": v} for k, v in response.headers.items()],
                "cookies": [],
                "content": {
                    "size": response_size,
                    "mimeType": mime_type,
                },
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": response_size,
            },
            "cache": {},
            "timings": {
                "send": 0,
                "wait": round(elapsed_ms, 3),
                "receive": 0,
            },
        }
