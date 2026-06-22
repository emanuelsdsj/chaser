# Browser Rendering

For JavaScript-heavy pages that are empty without a browser, Chaser integrates Playwright. Browser requests run through the same Engine and Pipeline as regular HTTP requests — you mix both in a single crawl.

## Setup

```bash
pip install "chaser[browser]"
playwright install chromium
```

## Per-request browser fetching

Set `use_browser=True` on any `Request` and enable the browser in the Engine:

```python
from chaser import Engine, Request, Trapper


class SpaTrapper(Trapper):
    def start_requests(self):
        return [Request(url="https://spa.example.com", use_browser=True)]

    async def parse(self, response):
        title = response.selector.css("h1::text").get("")
        ...


engine = Engine(browser=True)
await engine.run(SpaTrapper())
```

Regular requests (without `use_browser=True`) are still fetched via the httpx pool — only flagged requests go through Playwright.

## Browser pool

By default, each browser request opens a new Playwright page and closes it after the response is collected. The `BrowserPool` reuses pages across requests, which is significantly faster for crawls with many browser requests.

```python
from chaser import BrowserPool, Engine

pool = BrowserPool(size=4)   # keep 4 pages open concurrently
engine = Engine(browser=pool)
await engine.run(SpaTrapper())
```

The pool manages a single browser process with multiple pages. `size` controls the maximum number of concurrent page slots.

## Stealth mode

Sites that detect headless browsers can be bypassed with `StealthConfig`. It rotates user agents, viewports, timezones, and locales, and patches `navigator.webdriver` so the browser looks more like a real user.

```python
from chaser import BrowserPool, Engine, StealthConfig

stealth = StealthConfig(
    user_agents=["Mozilla/5.0 ...", "Mozilla/5.0 ..."],
    viewports=[(1920, 1080), (1366, 768), (1440, 900)],
    locales=["en-US", "en-GB"],
    timezones=["America/New_York", "Europe/London"],
)
pool = BrowserPool(size=4, stealth=stealth)
engine = Engine(browser=pool)
```

Each request gets a randomly selected combination of UA, viewport, locale, and timezone. The browser context is isolated per request slot when stealth is enabled.

## HAR recording in browser mode

`HarWriter` works with both httpx and browser requests:

```python
from chaser import Engine, HarWriter

async with HarWriter("crawl.har") as har:
    engine = Engine(browser=True, hooks=[har])
    await engine.run(SpaTrapper())
```

## Direct BrowserClient

For scripts that don't need the full Engine, use `BrowserClient` directly:

```python
from chaser import BrowserClient, Request

async with BrowserClient() as client:
    response = await client.fetch(Request(url="https://example.com"))
    print(response.text[:200])
```
