from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from chaser.trapper.base import ParseYield, Trapper

if TYPE_CHECKING:
    from chaser.net.response import Response


class CrawlTrapper(Trapper):
    """Trapper that auto-follows all anchor links found on each page.

    Set ``allowed_domains`` to restrict crawling to specific hosts.
    Override ``parse_item()`` to extract data from each page — the default
    implementation yields nothing, so subclassing is only required when you
    actually want items.

    Example::

        class BlogTrapper(CrawlTrapper):
            name = "blog"
            start_urls = ["https://example.com/blog"]
            allowed_domains = ["example.com"]

            async def parse_item(self, response):
                yield ArticleItem(
                    url=response.url,
                    title=response.selector.css("h1::text").get(""),
                )
    """

    allowed_domains: list[str] = []
    deny_extensions: list[str] = [
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "zip",
        "tar",
        "gz",
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "svg",
        "ico",
        "css",
        "js",
        "mp4",
        "mp3",
        "avi",
        "mov",
        "woff",
        "woff2",
        "ttf",
        "eot",
    ]

    def _is_allowed(self, url: str) -> bool:
        if not self.allowed_domains:
            return True
        host = urlparse(url).netloc
        return any(host == domain or host.endswith("." + domain) for domain in self.allowed_domains)

    def _has_denied_ext(self, url: str) -> bool:
        path = urlparse(url).path.lower().split("?")[0]
        return any(path.endswith("." + ext) for ext in self.deny_extensions)

    async def parse(self, response: Response) -> AsyncIterator[ParseYield]:
        async for item in self.parse_item(response):
            yield item

        from chaser.net.request import Request

        for href in response.selector.css("a::attr(href)").getall():
            href = href.strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            url = urljoin(response.url, href)
            if not url.startswith(("http://", "https://")):
                continue
            if self._is_allowed(url) and not self._has_denied_ext(url):
                yield Request(url=url, meta={"trapper": self.name})

    async def parse_item(self, response: Response) -> AsyncIterator[ParseYield]:
        """Override to extract items from each crawled page."""
        return
        yield  # pragma: no cover
