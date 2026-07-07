#!/usr/bin/env python3
"""Called by container cron — refreshes knowledge base from andestech.com."""
from __future__ import annotations

import os
import sys

import httpx


def main() -> int:
    secret = os.getenv("CRON_SECRET", "").strip()
    if not secret:
        print("scheduled reindex skipped: CRON_SECRET not set", file=sys.stderr)
        return 0

    port = os.getenv("PORT", "8000")
    url = f"http://127.0.0.1:{port}/reindex"
    print(f"scheduled reindex starting → {url}")

    try:
        resp = httpx.post(
            url,
            headers={"X-Cron-Secret": secret},
            timeout=3600.0,
        )
        print(resp.status_code, resp.text[:500])
        return 0 if resp.is_success else 1
    except Exception as exc:
        print(f"scheduled reindex failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
