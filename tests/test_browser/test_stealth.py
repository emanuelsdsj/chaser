from __future__ import annotations

import pytest

from chaser.browser.stealth import (
    STEALTH_INIT_SCRIPT,
    StealthConfig,
    _TIMEZONES,
    _USER_AGENTS,
    _VIEWPORTS,
)


class TestStealthConfig:
    def test_defaults_populated(self) -> None:
        cfg = StealthConfig()
        assert len(cfg.user_agents) > 0
        assert len(cfg.viewports) > 0
        assert len(cfg.timezones) > 0
        assert len(cfg.locales) > 0

    def test_defaults_use_module_pools(self) -> None:
        cfg = StealthConfig()
        assert cfg.user_agents == _USER_AGENTS
        assert cfg.viewports == _VIEWPORTS
        assert cfg.timezones == _TIMEZONES

    def test_custom_pools(self) -> None:
        ua = ["Mozilla/5.0 (custom)"]
        vp = [{"width": 800, "height": 600}]
        tz = ["UTC"]
        loc = ["pt-BR"]
        cfg = StealthConfig(user_agents=ua, viewports=vp, timezones=tz, locales=loc)
        assert cfg.user_agents == ua
        assert cfg.viewports == vp
        assert cfg.timezones == tz
        assert cfg.locales == loc

    def test_random_context_options_returns_required_keys(self) -> None:
        cfg = StealthConfig()
        opts = cfg.random_context_options()
        assert set(opts.keys()) == {"user_agent", "viewport", "timezone_id", "locale"}

    def test_random_context_options_values_come_from_pools(self) -> None:
        cfg = StealthConfig()
        opts = cfg.random_context_options()
        assert opts["user_agent"] in cfg.user_agents
        assert opts["viewport"] in cfg.viewports
        assert opts["timezone_id"] in cfg.timezones
        assert opts["locale"] in cfg.locales

    def test_random_context_options_with_single_entry_pools(self) -> None:
        ua = ["only-agent"]
        vp = [{"width": 1024, "height": 768}]
        tz = ["Europe/London"]
        loc = ["en-GB"]
        cfg = StealthConfig(user_agents=ua, viewports=vp, timezones=tz, locales=loc)
        opts = cfg.random_context_options()
        assert opts["user_agent"] == "only-agent"
        assert opts["viewport"] == {"width": 1024, "height": 768}
        assert opts["timezone_id"] == "Europe/London"
        assert opts["locale"] == "en-GB"

    def test_randomness_across_calls(self) -> None:
        """Pool of many options should produce variation across many calls."""
        cfg = StealthConfig()
        results = {cfg.random_context_options()["user_agent"] for _ in range(50)}
        # With 13+ user agents, 50 draws should hit at least 2 distinct values
        assert len(results) > 1

    def test_instances_are_independent(self) -> None:
        """Modifying one instance should not affect defaults in another."""
        cfg1 = StealthConfig()
        cfg2 = StealthConfig()
        cfg1.user_agents.clear()
        assert len(cfg2.user_agents) > 0

    def test_stealth_init_script_disables_webdriver(self) -> None:
        assert "webdriver" in STEALTH_INIT_SCRIPT
        assert "undefined" in STEALTH_INIT_SCRIPT


class TestBrowserClientStealth:
    """Unit tests for BrowserClient stealth integration (no real Playwright)."""

    @pytest.mark.asyncio
    async def test_stealth_stored_on_init(self) -> None:
        from chaser.browser.client import BrowserClient

        cfg = StealthConfig()
        client = BrowserClient(stealth=cfg)
        assert client._stealth is cfg

    @pytest.mark.asyncio
    async def test_no_stealth_by_default(self) -> None:
        from chaser.browser.client import BrowserClient

        client = BrowserClient()
        assert client._stealth is None

    @pytest.mark.asyncio
    async def test_fetch_with_stealth_uses_new_context(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from chaser.browser.client import BrowserClient
        from chaser.net.request import Request

        pw_resp = AsyncMock()
        pw_resp.status = 200
        pw_resp.all_headers = AsyncMock(return_value={"content-type": "text/html"})

        page = AsyncMock()
        page.url = "https://example.com/"
        page.goto = AsyncMock(return_value=pw_resp)
        page.content = AsyncMock(return_value="<html></html>")
        page.set_extra_http_headers = AsyncMock()
        page.add_init_script = AsyncMock()

        ctx = AsyncMock()
        ctx.new_page = AsyncMock(return_value=page)
        ctx.close = AsyncMock()

        browser = AsyncMock()
        browser.new_context = AsyncMock(return_value=ctx)
        browser.new_page = AsyncMock()  # should NOT be called

        client = BrowserClient(stealth=StealthConfig())
        client._browser = browser

        await client.fetch(Request(url="https://example.com/"))

        browser.new_context.assert_called_once()
        browser.new_page.assert_not_called()
        ctx.close.assert_called_once()
        page.add_init_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_without_stealth_uses_new_page(self) -> None:
        from unittest.mock import AsyncMock

        from chaser.browser.client import BrowserClient
        from chaser.net.request import Request

        pw_resp = AsyncMock()
        pw_resp.status = 200
        pw_resp.all_headers = AsyncMock(return_value={})

        page = AsyncMock()
        page.url = "https://example.com/"
        page.goto = AsyncMock(return_value=pw_resp)
        page.content = AsyncMock(return_value="<html></html>")
        page.set_extra_http_headers = AsyncMock()

        browser = AsyncMock()
        browser.new_page = AsyncMock(return_value=page)
        browser.new_context = AsyncMock()  # should NOT be called

        client = BrowserClient()
        client._browser = browser

        await client.fetch(Request(url="https://example.com/"))

        browser.new_page.assert_called_once()
        browser.new_context.assert_not_called()


class TestBrowserPoolStealth:
    def test_stealth_stored_on_init(self) -> None:
        from chaser.browser.pool import BrowserPool

        cfg = StealthConfig()
        pool = BrowserPool(stealth=cfg)
        assert pool._stealth is cfg

    def test_no_stealth_by_default(self) -> None:
        from chaser.browser.pool import BrowserPool

        pool = BrowserPool()
        assert pool._stealth is None

    @pytest.mark.asyncio
    async def test_new_slot_without_stealth_creates_bare_page(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from chaser.browser.pool import BrowserPool

        page = AsyncMock()
        browser = AsyncMock()
        browser.new_page = AsyncMock(return_value=page)
        browser.new_context = AsyncMock()  # should NOT be called

        pool = BrowserPool()
        pool._browser = browser

        slot = await pool._new_slot()

        assert slot.context is None
        assert slot.page is page
        browser.new_page.assert_called_once()
        browser.new_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_slot_with_stealth_creates_context(self) -> None:
        from unittest.mock import AsyncMock

        from chaser.browser.pool import BrowserPool

        page = AsyncMock()
        page.add_init_script = AsyncMock()

        ctx = AsyncMock()
        ctx.new_page = AsyncMock(return_value=page)

        browser = AsyncMock()
        browser.new_context = AsyncMock(return_value=ctx)
        browser.new_page = AsyncMock()  # should NOT be called

        pool = BrowserPool(stealth=StealthConfig())
        pool._browser = browser

        slot = await pool._new_slot()

        assert slot.context is ctx
        assert slot.page is page
        browser.new_context.assert_called_once()
        browser.new_page.assert_not_called()
        page.add_init_script.assert_called_once()
