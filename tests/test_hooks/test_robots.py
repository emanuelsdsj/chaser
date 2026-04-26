from __future__ import annotations

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
        with patch.object(RobotFileParser, "read", side_effect=OSError("refused")):
            result = await hook.before_request(Request("http://example.com/page"))
        assert result.url == "http://example.com/page"

    async def test_respects_custom_user_agent(self) -> None:
        robots = "User-agent: badbot\nDisallow: /\nUser-agent: *\nAllow: /\n"
        hook = RobotsHook(user_agent="badbot")
        hook._parsers["http://example.com"] = _parser(robots)
        req = Request("http://example.com/anything")
        with pytest.raises(RobotsDisallowedError):
            await hook.before_request(req)
