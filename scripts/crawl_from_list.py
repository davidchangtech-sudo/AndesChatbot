#!/usr/bin/env python3
"""Crawl URLs from data/crawl_urls.txt — skips slow sitemap discovery."""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

URL_FILE = ROOT / "data" / "crawl_urls.txt"


async def main() -> int:
    from app.config import get_settings
    from app.reindex import run_reindex

    if not URL_FILE.exists():
        print(f"Missing {URL_FILE} — run scripts/build_url_list.sh first", file=sys.stderr)
        return 1

    raw = [ln.strip() for ln in URL_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    settings = get_settings()
    print(
        f"Crawl from list: up to {settings.max_crawl_pages} of {len(raw)} URLs",
        flush=True,
    )
    result = await run_reindex(settings, url_list=raw)
    print(result, flush=True)
    return 0 if result.get("ok") and result.get("chunks_stored", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
