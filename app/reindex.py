from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.chunker import chunk_text
from app.config import Settings
from app.crawler import SiteCrawler
from app.gemini_client import GeminiClient
from app.store import get_store

logger = logging.getLogger(__name__)


async def _embed_with_retry(gemini: GeminiClient, text: str, url: str, chunk_index: int) -> list[float] | None:
    for attempt in range(5):
        try:
            return await asyncio.to_thread(gemini.embed_document, text)
        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 2 ** attempt
                logger.warning("Rate limited, retry in %ss (%s)", wait, url)
                await asyncio.sleep(wait)
                continue
            logger.warning("Embed failed for %s chunk %s: %s", url, chunk_index, exc)
            return None
    logger.warning("Embed failed after retries for %s chunk %s", url, chunk_index)
    return None


async def run_reindex(settings: Settings, url_list: list[str] | None = None) -> dict:
    from app.http_client import configure_crawl

    configure_crawl(settings.crawl_delay_seconds, settings.crawl_wordfence_cooldown)

    crawler = SiteCrawler(
        base_url=settings.crawl_base_url,
        sitemap_urls=settings.sitemap_url_list,
        max_pages=settings.max_crawl_pages,
        crawl_concurrency=settings.crawl_concurrency,
        sitemap_concurrency=settings.sitemap_concurrency,
    )
    if url_list is not None:
        urls = []
        for raw in url_list[: settings.max_crawl_pages]:
            norm = crawler._normalize(raw)
            if norm and crawler._should_crawl(norm):
                urls.append(norm)
        logger.info("Using %d URLs from provided list", len(urls))
    else:
        urls = await crawler.discover_urls()
        logger.info("Discovered %d URLs", len(urls))

    from app.crawl_progress import write_progress

    write_progress(
        status="running",
        total_urls=len(urls),
        pages_indexed=0,
        chunks_stored=0,
        message=f"Crawling {len(urls)} URLs (concurrency={settings.crawl_concurrency})",
    )

    gemini = GeminiClient(settings)
    store = get_store(settings)

    already: set[str] = set()
    if hasattr(store, "indexed_urls"):
        already = store.indexed_urls()
    if already:
        before = len(urls)
        norm_done = {u.rstrip("/") for u in already}
        urls = [u for u in urls if u.rstrip("/") not in norm_done]
        logger.info("Resume: %d already indexed, %d remaining", before - len(urls), len(urls))

    from app.http_client import async_client

    pages_ok = len(already)
    chunks_stored = getattr(store, "chunk_count", lambda: 0)()
    cleared = len(already) > 0
    state_lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, settings.crawl_concurrency))

    async def process_url(client, url: str) -> None:
        nonlocal pages_ok, chunks_stored, cleared
        async with sem:
            page = await crawler.fetch_page(client, url)
            if not page:
                return

            async with state_lock:
                if not cleared:
                    store.clear_chunks()
                    cleared = True

            title, text, images = page
            images_json = json.dumps(images) if images else None
            chunks = chunk_text(text)
            if not chunks:
                return

            page_rows: list[dict] = []
            for ch in chunks:
                embedding = await _embed_with_retry(gemini, ch.content, url, ch.chunk_index)
                if embedding is None:
                    continue
                page_rows.append(
                    {
                        "url": url,
                        "title": title,
                        "content": ch.content,
                        "word_count": ch.word_count,
                        "chunk_index": ch.chunk_index,
                        "embedding": embedding,
                        "images_json": images_json,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            if not page_rows:
                return

            async with state_lock:
                store.upsert_chunks(page_rows)
                pages_ok += 1
                chunks_stored += len(page_rows)
                logger.info("Indexed page %s/%s: %s (%s chunks)", pages_ok, len(urls), url, len(page_rows))
                write_progress(
                    status="running",
                    total_urls=len(urls),
                    pages_indexed=pages_ok,
                    chunks_stored=chunks_stored,
                    current_url=url,
                    message=f"Indexed {pages_ok}/{len(urls)} pages",
                )

            if settings.crawl_delay_seconds > 0:
                await asyncio.sleep(settings.crawl_delay_seconds)

    async with async_client(timeout=60.0) as client:
        results = await asyncio.gather(*(process_url(client, url) for url in urls), return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error("Page worker failed: %s", r)

    if not cleared:
        write_progress(
            status="failed",
            total_urls=len(urls),
            pages_indexed=0,
            chunks_stored=0,
            message="Could not fetch any pages (503 or network)",
        )
        return {
            "ok": False,
            "pages_crawled": 0,
            "chunks_stored": 0,
            "message": (
                f"Reindex aborted: could not fetch any of {len(urls)} URLs "
                "(site may be down or returning 503). Existing index was kept."
            ),
        }

    write_progress(
        status="done",
        total_urls=len(urls),
        pages_indexed=pages_ok,
        chunks_stored=chunks_stored,
        message=f"Done — {pages_ok} pages, {chunks_stored} chunks",
    )
    return {
        "ok": True,
        "pages_crawled": pages_ok,
        "chunks_stored": chunks_stored,
        "message": f"Reindexed {pages_ok} pages ({chunks_stored} chunks) from {len(urls)} discovered URLs.",
    }
