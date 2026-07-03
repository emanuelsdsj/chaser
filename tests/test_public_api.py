"""Guards the top-level public API surface against accidental breakage.

If this test fails after you added, renamed, or removed something in
`chaser.__all__`, update `EXPECTED_PUBLIC_API` deliberately — a failure here
means a change to what 1.x promises to keep stable.
"""

import chaser

EXPECTED_PUBLIC_API = {
    "Engine",
    "CrawlStats",
    "Trapper",
    "CrawlTrapper",
    "SitemapTrapper",
    "Item",
    "ItemLoader",
    "strip",
    "join",
    "first",
    "take_all",
    "compose",
    "HttpCache",
    "Request",
    "Response",
    "Pipeline",
    "Stage",
    "JsonlStore",
    "CsvStore",
    "DbStore",
    "ParquetStore",
    "S3Store",
    "GCSStore",
    "DuplicateFilter",
    "SqliteFrontier",
    "RedisFrontier",
    "RetryPolicy",
    "ProxyPool",
    "RateLimitHook",
    "CookieJarHook",
    "RobotsHook",
    "RobotsDisallowedError",
    "AutoThrottleHook",
    "BandwidthThrottleHook",
    "FetchHook",
    "RequestAborted",
    "BrowserClient",
    "BrowserPool",
    "StealthConfig",
    "HarWriter",
    "ChaserSettings",
    "__version__",
}


def test_all_matches_expected_public_api():
    assert set(chaser.__all__) == EXPECTED_PUBLIC_API


def test_all_has_no_duplicates():
    assert len(chaser.__all__) == len(set(chaser.__all__))


def test_every_exported_name_is_importable():
    for name in chaser.__all__:
        assert hasattr(chaser, name), f"chaser.__all__ lists {name!r} but it is not importable"


def test_version_is_a_string():
    assert isinstance(chaser.__version__, str)
    assert chaser.__version__.count(".") == 2
