#!/usr/bin/env python3
"""One polite request to andestech.com — use before any full reindex."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def main() -> int:
    from app.http_client import async_client, configure_crawl, fetch_with_retry

    configure_crawl(delay_seconds=10.0, wordfence_cooldown=300.0)
    url = "https://www.andestech.com/en/"

    print(f"Single gentle GET (10s throttle, max 2 tries): {url}")
    async with async_client(timeout=45.0) as client:
        try:
            resp = await fetch_with_retry(client, url, max_attempts=2)
            print(f"OK — HTTP {resp.status_code}, {len(resp.text)} bytes")
            return 0
        except Exception as exc:
            print(f"Blocked or unreachable: {exc}")
            print("Wait 1+ hour before crawling. Ask IT to whitelist your IP in Wordfence.")
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
