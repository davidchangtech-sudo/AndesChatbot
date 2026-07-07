#!/usr/bin/env python3
"""Crawl the full Andes /en/ site and rebuild the local (or Supabase) knowledge base."""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def main() -> int:
    from app.config import get_settings
    from app.reindex import run_reindex

    settings = get_settings()
    print(f"Full reindex starting (max_pages={settings.max_crawl_pages})...")
    result = await run_reindex(settings)
    print(result)
    if not result.get("ok") or result["chunks_stored"] == 0:
        print(result["message"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
