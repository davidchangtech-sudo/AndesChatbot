from __future__ import annotations
import asyncio
import re
import xml.etree.ElementTree as ET
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from app.extractor import extract_page, is_english_path
from app.images import extract_images
from app.http_client import async_client, fetch_with_retry

SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SKIP_PATH_PARTS = ("/feed", "/wp-json", "/wp-admin", "/wp-content", "/comments/feed")


class SiteCrawler:
    def __init__(
        self,
        base_url: str,
        sitemap_urls: list[str],
        max_pages: int = 500,
        timeout: float = 20.0,
        crawl_concurrency: int = 1,
        sitemap_concurrency: int = 1,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        parsed = urlparse(self.base_url)
        self.host = parsed.netloc.replace("www.", "")
        self.sitemap_urls = sitemap_urls
        self.max_pages = max_pages
        self.timeout = timeout
        self.crawl_concurrency = max(1, crawl_concurrency)
        self.sitemap_concurrency = max(1, sitemap_concurrency)
        self._seen: set[str] = set()

    async def discover_urls(self) -> list[str]:
        sitemap_urls: list[str] = []
        try:
            sitemap_urls = await asyncio.wait_for(self._urls_from_sitemaps(), timeout=180.0)
        except asyncio.TimeoutError:
            pass

        if len(sitemap_urls) >= 20:
            return sitemap_urls[: self.max_pages]

        self._seen.clear()
        crawled = await self._crawl_internal_links()
        merged = self._merge_urls(sitemap_urls, crawled)
        if merged:
            return merged[: self.max_pages]
        return [self.base_url.rstrip("/")]

    def _merge_urls(self, *groups: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for raw in group:
                norm = self._normalize(raw)
                if not norm or norm in seen or not self._should_crawl(norm):
                    continue
                seen.add(norm)
                out.append(norm)
        return out

    def _should_crawl(self, url: str) -> bool:
        if not is_english_path(url, self.host):
            return False
        path = urlparse(url).path.lower()
        return not any(part in path for part in SKIP_PATH_PARTS)

    async def fetch_page(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[str, str, list[dict]] | None:
        try:
            resp = await fetch_with_retry(client, url)
            if "text/html" not in (resp.headers.get("content-type") or ""):
                return None
            page_url = str(resp.url)
            title, text = extract_page(resp.text, page_url)
            if len(text.split()) < 30:
                return None
            images = extract_images(resp.text, page_url)
            return title, text, images
        except (httpx.HTTPError, ValueError):
            return None

    async def _urls_from_sitemaps(self) -> list[str]:
        urls: list[str] = []
        async with async_client(timeout=self.timeout) as client:
            for sitemap_url in self.sitemap_urls:
                found = await self._parse_sitemap_recursive(client, sitemap_url)
                if found:
                    urls.extend(found)
                if urls:
                    break
                await asyncio.sleep(3.0)

        filtered = []
        for u in urls:
            u = self._normalize(u)
            if u and self._should_crawl(u) and u not in self._seen:
                self._seen.add(u)
                filtered.append(u)
        return filtered

    async def _parse_sitemap_recursive(
        self, client: httpx.AsyncClient, sitemap_url: str
    ) -> list[str]:
        try:
            resp = await fetch_with_retry(client, sitemap_url)
        except httpx.HTTPError:
            return []

        ctype = (resp.headers.get("content-type") or "").lower()
        if "xml" not in ctype and "text/plain" not in ctype:
            return []

        root = _parse_xml_root(resp.content)
        if root is None:
            return []

        tag = _local_name(root.tag)
        if tag == "sitemapindex":
            child_urls = []
            for loc in root.findall(".//sm:loc", SITEMAP_NS) + root.findall(".//loc"):
                if loc.text:
                    child_urls.append(loc.text.strip())
            if not child_urls and root.findall(".//{*}sitemap"):
                for s in root.findall(".//{*}sitemap"):
                    loc = s.find("{*}loc")
                    if loc is not None and loc.text:
                        child_urls.append(loc.text.strip())

            return await self._fetch_child_sitemaps(client, child_urls)

        if tag == "urlset":
            page_urls = []
            for loc in root.findall(".//sm:loc", SITEMAP_NS) + root.findall(".//loc"):
                if loc.text:
                    page_urls.append(loc.text.strip())
            return [u for u in page_urls if is_english_path(u, self.host)]

        return []

    async def _fetch_child_sitemaps(
        self, client: httpx.AsyncClient, child_urls: list[str]
    ) -> list[str]:
        sem = asyncio.Semaphore(self.sitemap_concurrency)
        all_pages: list[str] = []

        async def fetch_child(child: str) -> list[str]:
            async with sem:
                try:
                    return await asyncio.wait_for(
                        self._parse_sitemap_recursive(client, child),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    return []

        batch_size = self.sitemap_concurrency
        for i in range(0, len(child_urls), batch_size):
            batch = child_urls[i : i + batch_size]
            results = await asyncio.gather(*(fetch_child(c) for c in batch))
            for pages in results:
                all_pages.extend(pages)
            if len(all_pages) >= self.max_pages * 2:
                break
        return all_pages

    async def _crawl_internal_links(self) -> list[str]:
        queue: deque[str] = deque([self.base_url])
        collected: list[str] = []
        workers = self.crawl_concurrency
        sem = asyncio.Semaphore(workers)

        async with async_client(timeout=self.timeout) as client:

            async def fetch_one(norm: str) -> tuple[str, str] | None:
                async with sem:
                    try:
                        resp = await fetch_with_retry(client, norm)
                    except httpx.HTTPError:
                        return None
                    if "text/html" not in (resp.headers.get("content-type") or ""):
                        return None
                    return str(resp.url), resp.text

            while queue and len(collected) < self.max_pages:
                batch: list[str] = []
                while queue and len(batch) < workers * 2:
                    candidate = self._normalize(queue.popleft())
                    if not candidate or candidate in self._seen or not self._should_crawl(candidate):
                        continue
                    self._seen.add(candidate)
                    batch.append(candidate)

                if not batch:
                    break

                results = await asyncio.gather(*(fetch_one(u) for u in batch))
                for item in results:
                    if not item or len(collected) >= self.max_pages:
                        continue
                    final_url, html = item
                    collected.append(final_url)
                    for link in _extract_links(html, final_url):
                        norm_link = self._normalize(link)
                        if norm_link and norm_link not in self._seen and self._should_crawl(norm_link):
                            queue.append(norm_link)

        return collected

    def _normalize(self, url: str) -> str | None:
        url, _ = urldefrag(url)
        if not url.startswith("http"):
            url = urljoin(self.base_url, url)
        parsed = urlparse(url)
        if parsed.netloc.replace("www.", "") != self.host:
            return None
        skip_ext = (".pdf", ".jpg", ".png", ".zip", ".xml", ".css", ".js")
        if parsed.path.lower().endswith(skip_ext):
            return None
        return url.rstrip("/") or url


def _parse_xml_root(content: bytes) -> ET.Element | None:
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        text = content.decode("utf-8", errors="ignore")
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", text, flags=re.I)
        if not locs:
            return None
        pseudo = "<urlset>" + "".join(f"<url><loc>{loc}</loc></url>" for loc in locs) + "</urlset>"
        try:
            return ET.fromstring(pseudo)
        except ET.ParseError:
            return None


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_links(html: str, base_url: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    out: list[str] = []
    for href in hrefs:
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        out.append(urljoin(base_url, href))
    return out
