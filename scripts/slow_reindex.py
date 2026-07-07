#!/usr/bin/env python3
"""
Gentle full-site reindex — slow requests to reduce Wordfence blocks.

Defaults (~1 page every 6s + long 503 backoff):
  CRAWL_DELAY_SECONDS=6
  CRAWL_WORDFENCE_COOLDOWN=180
  CRAWL_CONCURRENCY=1
  SITEMAP_CONCURRENCY=1

Override in .env or environment before running.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Gentle defaults (only if not already set in .env)
os.environ.setdefault("CRAWL_DELAY_SECONDS", "10")
os.environ.setdefault("CRAWL_WORDFENCE_COOLDOWN", "300")
os.environ.setdefault("MAX_CRAWL_PAGES", "150")
os.environ.setdefault("CRAWL_CONCURRENCY", "1")
os.environ.setdefault("SITEMAP_CONCURRENCY", "1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("slow_reindex")


async def main() -> int:
    from app.config import get_settings
    from app.reindex import run_reindex

    get_settings.cache_clear()
    settings = get_settings()

    est_min = (settings.max_crawl_pages * settings.crawl_delay_seconds) / 60
    print(
        "Slow reindex starting\n"
        f"  max_pages={settings.max_crawl_pages}\n"
        f"  delay={settings.crawl_delay_seconds}s between pages\n"
        f"  wordfence_cooldown={settings.crawl_wordfence_cooldown}s on 503\n"
        f"  (~{est_min:.0f} min minimum if all pages fetch; often longer with retries)\n"
    )

    result = await run_reindex(settings)
    print(result)
    if result.get("pages_crawled", 0) == 0:
        print(
            "\nNo pages fetched. The site may still be blocking this IP (503).\n"
            "Wait 30–60 min, or ask Andes IT to whitelist your IP in Wordfence,\n"
            "then run this script again.",
            file=sys.stderr,
        )
        return 1
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
