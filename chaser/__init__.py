"""Chaser — a fast, async web crawling framework built on modern Python."""

from chaser.browser.client import BrowserClient
from chaser.browser.pool import BrowserPool
from chaser.browser.stealth import StealthConfig
from chaser.config.settings import ChaserSettings
from chaser.engine.runner import Engine
from chaser.engine.stats import CrawlStats
from chaser.frontier.redis_frontier import RedisFrontier
from chaser.frontier.sqlite import SqliteFrontier
from chaser.hooks.autothrottle import AutoThrottleHook
from chaser.hooks.bandwidth import BandwidthThrottleHook
from chaser.hooks.base import FetchHook, RequestAborted
from chaser.hooks.cookies import CookieJarHook
from chaser.hooks.har import HarWriter
from chaser.hooks.proxy import ProxyPool
from chaser.hooks.ratelimit import RateLimitHook
from chaser.hooks.retry import RetryPolicy
from chaser.hooks.robots import RobotsDisallowedError, RobotsHook
from chaser.item.base import Item
from chaser.item.loader import ItemLoader, compose, first, join, strip, take_all
from chaser.net.cache import HttpCache
from chaser.net.request import Request
from chaser.net.response import Response
from chaser.pipeline.base import Pipeline, Stage
from chaser.pipeline.filters import DuplicateFilter
from chaser.pipeline.store.csv import CsvStore
from chaser.pipeline.store.db import DbStore
from chaser.pipeline.store.gcs import GCSStore
from chaser.pipeline.store.jsonl import JsonlStore
from chaser.pipeline.store.parquet import ParquetStore
from chaser.pipeline.store.s3 import S3Store
from chaser.trapper.base import Trapper
from chaser.trapper.crawl import CrawlTrapper
from chaser.trapper.sitemap import SitemapTrapper

__version__ = "1.0.0"

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
]
