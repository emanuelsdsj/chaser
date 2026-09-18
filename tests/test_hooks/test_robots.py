from __future__ import annotations

import urllib.error
import urllib.request
from unittest.mock import patch
from urllib.robotparser import RobotFileParser

import pytest

from chaser.hooks.robots import RobotsDisallowedError, RobotsHook
from chaser.net.request import Request

ROBOTS = "User-agent: *\nDisallow: /private/\nAllow: /\n"


def _parser(content: str) -> RobotFileParser:
    p = RobotFileParser()
    p.parse(content.splitlines())
    return p


class TestRobotsHook:
    async def test_allows_permitted_url(self) -> None:
        hook = RobotsHook()
        hook._parsers["http://example.com"] = _parser(ROBOTS)
        req = Request("http://example.com/public/page")
        result = await hook.before_request(req)
        assert result is req

    async def test_raises_for_disallowed_url(self) -> None:
        hook = RobotsHook()
        hook._parsers["http://example.com"] = _parser(ROBOTS)
        req = Request("http://example.com/private/secret")
        with pytest.raises(RobotsDisallowedError):
            await hook.before_request(req)

    async def test_robots_txt_fetched_once_per_domain(self) -> None:
        hook = RobotsHook()
        hook._parsers["http://example.com"] = _parser(ROBOTS)
        req = Request("http://example.com/page")
        await hook.before_request(req)
        await hook.before_request(req)
        # Pre-loaded parser still the only entry — no duplicate fetch
        assert len(hook._parsers) == 1

    async def test_allows_request_when_robots_fetch_fails(self) -> None:
        hook = RobotsHook()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = await hook.before_request(Request("http://example.com/page"))
        assert result.url == "http://example.com/page"

    async def test_respects_custom_user_agent(self) -> None:
        robots = "User-agent: badbot\nDisallow: /\nUser-agent: *\nAllow: /\n"
        hook = RobotsHook(user_agent="badbot")
        hook._parsers["http://example.com"] = _parser(robots)
        req = Request("http://example.com/anything")
        with pytest.raises(RobotsDisallowedError):
            await hook.before_request(req)

    async def test_fetch_sends_a_real_browser_user_agent(self) -> None:
        hook = RobotsHook()
        captured: list[urllib.request.Request] = []

        def fake_urlopen(
            request: urllib.request.Request, *args: object, **kwargs: object
        ) -> object:
            captured.append(request)
            raise urllib.error.URLError("stop before any real network call")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            await hook.before_request(Request("http://example.com/page"))

        assert len(captured) == 1
        ua = captured[0].get_header("User-agent")
        assert ua is not None
        assert "python-urllib" not in ua.lower()

    async def test_403_on_robots_txt_itself_does_not_block_the_crawl(self) -> None:
        """A WAF 403 on the *fetch* of robots.txt — a real, observed failure
        mode distinct from the site's actual policy — must not be mistaken
        for the site disallowing everything: no rules could be read, so none
        are enforced (matches the class's own documented "fetch fails for
        any reason -> allowed" contract, which stdlib's read() violates for
        401/403 specifically)."""
        hook = RobotsHook()
        error = urllib.error.HTTPError("http://example.com/robots.txt", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            result = await hook.before_request(Request("http://example.com/page"))
        assert result.url == "http://example.com/page"
