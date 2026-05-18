from __future__ import annotations

from unittest.mock import patch

from chaser.net.cache import HttpCache
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


def _req(url: str = "http://example.com/", method: str = "GET") -> Request:
    return Request(url=url, method=method)


def _resp(
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes = b"hello",
    url: str = "http://example.com/",
) -> Response:
    return Response(url=url, status=status, headers=Headers(headers or {}), body=body)


# ---------------------------------------------------------------------------
# Miss
# ---------------------------------------------------------------------------


class TestCacheMiss:
    def test_empty_cache(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        lookup = cache.lookup(_req())
        assert lookup.response is None
        assert not lookup.fresh
        assert lookup.conditional_headers == {}


# ---------------------------------------------------------------------------
# Store + fresh hit
# ---------------------------------------------------------------------------


class TestStore:
    def test_max_age_hit(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "max-age=3600"}))
        lookup = cache.lookup(req)
        assert lookup.fresh
        assert lookup.response is not None
        assert lookup.response.body == b"hello"

    def test_expired_max_age_not_fresh(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        with patch("chaser.net.cache.time.time", return_value=1000.0):
            cache.store(req, _resp(headers={"cache-control": "max-age=10"}))
        with patch("chaser.net.cache.time.time", return_value=1015.0):
            lookup = cache.lookup(req)
        assert not lookup.fresh

    def test_no_store_skipped(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "no-store"}))
        assert cache.lookup(req).response is None

    def test_no_cache_stored_but_stale(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "no-cache", "etag": '"v1"'}))
        lookup = cache.lookup(req)
        assert lookup.response is not None
        assert not lookup.fresh
        assert lookup.conditional_headers.get("if-none-match") == '"v1"'

    def test_post_not_cached(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        cache.store(_req(method="POST"), _resp(headers={"cache-control": "max-age=3600"}))
        assert cache.lookup(_req()).response is None

    def test_404_not_cached(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(status=404, headers={"cache-control": "max-age=3600"}))
        assert cache.lookup(req).response is None

    def test_no_ttl_no_validators_not_cached(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp())  # no cache headers at all
        assert cache.lookup(req).response is None

    def test_from_cache_flag_set(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "max-age=3600"}))
        lookup = cache.lookup(req)
        assert lookup.response is not None
        assert lookup.response.from_cache is True


# ---------------------------------------------------------------------------
# Expires header
# ---------------------------------------------------------------------------


class TestExpiresHeader:
    def test_future_expires_is_fresh(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"expires": "Thu, 01 Jan 2099 00:00:00 GMT"}))
        assert cache.lookup(req).fresh

    def test_past_expires_is_stale(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"expires": "Thu, 01 Jan 2015 00:00:00 GMT"}))
        assert not cache.lookup(req).fresh


# ---------------------------------------------------------------------------
# Conditional headers (ETag / Last-Modified)
# ---------------------------------------------------------------------------


class TestConditionalHeaders:
    def test_etag_becomes_if_none_match(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"etag": '"abc"'}))
        cond = cache.lookup(req).conditional_headers
        assert cond.get("if-none-match") == '"abc"'

    def test_last_modified_becomes_if_modified_since(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"last-modified": "Wed, 21 Oct 2015 07:28:00 GMT"}))
        cond = cache.lookup(req).conditional_headers
        assert "if-modified-since" in cond

    def test_both_validators_present(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(
            req,
            _resp(headers={"etag": '"v2"', "last-modified": "Wed, 21 Oct 2015 07:28:00 GMT"}),
        )
        cond = cache.lookup(req).conditional_headers
        assert "if-none-match" in cond
        assert "if-modified-since" in cond

    def test_fresh_entry_has_no_conditional_headers(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "max-age=3600", "etag": '"v1"'}))
        lookup = cache.lookup(req)
        assert lookup.fresh
        assert lookup.conditional_headers == {}


# ---------------------------------------------------------------------------
# Touch (304 revalidation)
# ---------------------------------------------------------------------------


class TestTouch:
    def test_touch_refreshes_expiry(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        with patch("chaser.net.cache.time.time", return_value=1000.0):
            cache.store(req, _resp(headers={"cache-control": "max-age=60", "etag": '"v1"'}))
        # At t=1070 the entry is expired
        with patch("chaser.net.cache.time.time", return_value=1070.0):
            assert not cache.lookup(req).fresh
            cache.touch(req)
        # After touch at t=1070, fresh until t=1130
        with patch("chaser.net.cache.time.time", return_value=1080.0):
            assert cache.lookup(req).fresh

    def test_touch_on_missing_entry_is_noop(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        cache.touch(_req())  # must not raise


# ---------------------------------------------------------------------------
# Corruption resilience
# ---------------------------------------------------------------------------


class TestCorruption:
    def test_corrupt_meta_returns_miss(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path)  # type: ignore[arg-type]
        req = _req()
        cache.store(req, _resp(headers={"cache-control": "max-age=3600"}))
        key = cache._key(req)
        cache._meta_path(key).write_text("not json {{{")
        assert cache.lookup(req).response is None
