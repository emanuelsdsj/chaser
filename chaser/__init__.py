"""Chaser — a fast, async web crawling framework built on modern Python."""

from chaser.browser.client import BrowserClient
from chaser.engine.runner import Engine
from chaser.engine.stats import CrawlStats
from chaser.hooks.autothrottle import AutoThrottleHook
from chaser.hooks.cookies import CookieJarHook
from chaser.hooks.proxy import ProxyPool
from chaser.hooks.ratelimit import RateLimitHook
from chaser.hooks.retry import RetryPolicy
from chaser.hooks.robots import RobotsHook
from chaser.item.base import Item
from chaser.item.loader import ItemLoader, compose, first, join, strip, take_all
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.pipeline.base import Pipeline, Stage
from chaser.pipeline.store.csv import CsvStore
from chaser.pipeline.store.jsonl import JsonlStore
from chaser.trapper.base import Trapper
from chaser.trapper.crawl import CrawlTrapper
from chaser.trapper.sitemap import SitemapTrapper

__version__ = "0.0.1"

__all__ = [
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
    "Request",
    "Response",
    "Pipeline",
    "Stage",
    "JsonlStore",
    "CsvStore",
    "RetryPolicy",
    "ProxyPool",
    "RateLimitHook",
    "CookieJarHook",
    "RobotsHook",
    "AutoThrottleHook",
    "BrowserClient",
    "__version__",
]
