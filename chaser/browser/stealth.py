from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

_USER_AGENTS: list[str] = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Firefox on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox on Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

_VIEWPORTS: list[dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 800},
    {"width": 1024, "height": 768},
    {"width": 1680, "height": 1050},
]

_TIMEZONES: list[str] = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "America/Vancouver",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Warsaw",
    "Europe/Amsterdam",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Asia/Singapore",
    "Asia/Shanghai",
    "Australia/Sydney",
    "Australia/Melbourne",
]

_LOCALES: list[str] = ["en-US", "en-GB", "en-CA", "en-AU"]

# Injected into every page to mask automation signals
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}};
"""


@dataclass
class StealthConfig:
    """Anti-detection configuration for browser-based fetching.

    Randomizes user agent, viewport, timezone, and locale per browser context
    to reduce fingerprinting surface. Each call to random_context_options()
    picks independently, so concurrent pages look like different visitors.

    Usage::

        stealth = StealthConfig()
        client = BrowserClient(stealth=stealth)

        # Narrow down to a specific region if needed
        stealth = StealthConfig(
            timezones=["America/New_York", "America/Chicago"],
            locales=["en-US"],
        )
    """

    user_agents: list[str] = field(default_factory=lambda: list(_USER_AGENTS))
    viewports: list[dict[str, int]] = field(default_factory=lambda: list(_VIEWPORTS))
    timezones: list[str] = field(default_factory=lambda: list(_TIMEZONES))
    locales: list[str] = field(default_factory=lambda: list(_LOCALES))

    def random_context_options(self) -> dict[str, Any]:
        """Return randomized kwargs for Playwright's new_context()."""
        return {
            "user_agent": random.choice(self.user_agents),
            "viewport": random.choice(self.viewports),
            "timezone_id": random.choice(self.timezones),
            "locale": random.choice(self.locales),
        }
