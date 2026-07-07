#!/usr/bin/env python3
"""
Monthly reindex — call the protected /reindex endpoint.

Cron example (1st of each month at 3:00 AM UTC):
  0 3 1 * * cd /path/to/Chatbot && .venv/bin/python scripts/monthly_reindex.py
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
CRON_SECRET = os.getenv("CRON_SECRET", "")


def main() -> int:
    if not CRON_SECRET:
        print("CRON_SECRET is not set in .env", file=sys.stderr)
        return 1

    resp = httpx.post(
        f"{API_URL}/reindex",
        headers={"X-Cron-Secret": CRON_SECRET},
        timeout=3600.0,
    )
    print(resp.status_code, resp.text)
    return 0 if resp.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
