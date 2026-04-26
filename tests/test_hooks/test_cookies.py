from __future__ import annotations

from chaser.hooks.cookies import CookieJarHook
from chaser.net.headers import Headers
from chaser.net.request import Request
from chaser.net.response import Response


def _response(url: str, set_cookie: str | None = None) -> Response:
    h = Headers()
    if set_cookie:
        h["set-cookie"] = set_cookie
    return Response(url=url, status=200, headers=h, body=b"")


class TestCookieJarHook:
    async def test_no_cookies_on_fresh_jar(self) -> None:
        hook = CookieJarHook()
        req = Request("http://example.com/")
        result = await hook.before_request(req)
        assert result.headers.get("cookie") is None

    async def test_stores_set_cookie_from_response(self) -> None:
        hook = CookieJarHook()
        await hook.after_response(_response("http://example.com/", "session=abc123"))
        assert hook._jar["example.com"]["session"] == "abc123"

    async def test_injects_stored_cookie_into_next_request(self) -> None:
        hook = CookieJarHook()
        await hook.after_response(_response("http://example.com/login", "token=xyz"))
        req = Request("http://example.com/dashboard")
        result = await hook.before_request(req)
        assert "token=xyz" in (result.headers.get("cookie") or "")

    async def test_cookies_are_isolated_by_domain(self) -> None:
        hook = CookieJarHook()
        await hook.after_response(_response("http://site-a.com/", "auth=secret"))
        req = Request("http://site-b.com/")
        result = await hook.before_request(req)
        assert result.headers.get("cookie") is None

    async def test_updates_existing_cookie_value(self) -> None:
        hook = CookieJarHook()
        await hook.after_response(_response("http://example.com/", "session=old"))
        await hook.after_response(_response("http://example.com/", "session=new"))
        assert hook._jar["example.com"]["session"] == "new"

    async def test_response_without_set_cookie_is_unchanged(self) -> None:
        hook = CookieJarHook()
        resp = _response("http://example.com/")
        result = await hook.after_response(resp)
        assert result is resp
        assert not hook._jar
