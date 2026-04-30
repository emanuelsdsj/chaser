from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from chaser.trapper.base import ParseYield, Trapper

if TYPE_CHECKING:
    from chaser.net.response import Response

_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_META_SITEMAP = "is_sitemap"


class SitemapTrapper(Trapper):
    """Trapper that discovers URLs through sitemap.xml files.

    If ``sitemap_urls`` is set, those are fetched directly.  Otherwise each
    ``start_urls`` entry has ``/sitemap.xml`` appended to its root.

    Sitemap indexes (``<sitemapindex>``) are followed recursively.
    Leaf sitemaps (``<urlset>``) produce normal fetch requests routed to
    ``parse_item()``.

    Example::

        class ShopTrapper(SitemapTrapper):
            name = "shop"
            sitemap_urls = ["https://shop.example.com/sitemap_products.xml"]

            async def parse_item(self, response):
                yield ProductItem(
                    url=response.url,
                    title=response.selector.css("h1::text").get(""),
                )
    """

    sitemap_urls: list[str] = []

    def start_requests(self) -> list[Any]:
        from chaser.net.request import Request

        if self.sitemap_urls:
            urls = self.sitemap_urls
        else:
            seen: set[str] = set()
            urls = []
            for u in self.start_urls:
                parsed = urlparse(u)
                root = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
                if root not in seen:
                    seen.add(root)
                    urls.append(root)

        return [Request(url=u, meta={"trapper": self.name, _META_SITEMAP: True}) for u in urls]

    async def parse(self, response: Response) -> AsyncIterator[ParseYield]:
        if response.request and response.request.meta.get(_META_SITEMAP):
            async for result in self._parse_sitemap(response):
                yield result
        else:
            async for item in self.parse_item(response):
                yield item

    async def _parse_sitemap(self, response: Response) -> AsyncIterator[ParseYield]:
        from chaser.net.request import Request

        try:
            root = ET.fromstring(response.body)
        except ET.ParseError:
            return

        local = root.tag.lower()
        if "sitemapindex" in local:
            for loc in root.findall(f".//{{{_NS}}}loc"):
                url = (loc.text or "").strip()
                if url:
                    yield Request(
                        url=url,
                        meta={"trapper": self.name, _META_SITEMAP: True},
                    )
        else:
            for loc in root.findall(f".//{{{_NS}}}loc"):
                url = (loc.text or "").strip()
                if url:
                    yield Request(url=url, meta={"trapper": self.name})

    async def parse_item(self, response: Response) -> AsyncIterator[ParseYield]:
        """Override to extract items from each discovered URL."""
        return
        yield  # pragma: no cover
