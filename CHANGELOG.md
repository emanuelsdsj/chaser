# Changelog

All notable changes to this project will be documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased]

## [0.0.1] — 2025-05-03

### Added

- `Engine` — async hub coordinating frontier, net client, trap layer, and pipeline
- `Frontier` — bloom filter deduplication (MurmurHash3 + bitarray) with BFS/DFS/score scheduling strategies
- `NetClient` — httpx connection pool with HTTP/2 by default, per-domain circuit breaker, SOCKS5 proxy support
- `Trapper` — abstract base class for defining crawl targets
- `CrawlTrapper` — auto-follows `<a>` links with `allowed_domains` and `deny_extensions` filtering
- `SitemapTrapper` — sitemap-driven crawl, recursively follows `<sitemapindex>` entries
- `Item` — Pydantic v2 base model for validated scraped items
- `ItemLoader` — field processor chains (`strip`, `join`, `first`, `take_all`, `compose`)
- `Selector` / `SelectorList` — CSS, XPath, JMESPath, and regex extraction (wraps parsel)
- `Pipeline` + `Stage` — async item processing chain
- `JsonlStore` — streaming JSONL output with append-safe concurrent writes
- `CsvStore` — streaming CSV with auto-header detection
- `DbStore` — async SQLAlchemy sink with auto table creation (via `chaser[db]` extra)
- `RetryPolicy` — exponential backoff with jitter
- `RateLimitHook` — per-domain token bucket rate limiting
- `CookieJarHook` — per-domain cookie jar, reads `Set-Cookie`, injects on next requests
- `RobotsHook` — cached `robots.txt` compliance per domain
- `ProxyPool` — round-robin proxy rotation with failure tracking
- `BrowserClient` — Playwright-based fetch client returning same `Response` interface (via `chaser[browser]` extra)
- `ChaserSettings` — configuration via `[tool.chaser]` in `pyproject.toml` and `CHASER_*` env vars
- CLI: `chaser run`, `chaser shell`, `chaser version`
- `Response.urljoin()` for relative URL resolution
- `Response.json_selector` property for JMESPath queries on JSON responses
