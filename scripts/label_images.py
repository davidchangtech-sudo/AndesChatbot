#!/usr/bin/env python3
"""Label crawled page images with Gemini vision and update the RAG database."""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.gemini_client import GeminiClient
from app.image_labels import ImageLabelStore, merge_labels_into_chunks

DB_PATH = ROOT / "data" / "rag.db"
LOG_PATH = ROOT / "data" / "label_images.log"


def log(msg: str) -> None:
    line = msg if msg.endswith("\n") else msg + "\n"
    print(msg, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def collect_unique_images(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return [(image_url, page_url, page_title), ...]"""
    rows = conn.execute(
        """
        select distinct url, title, images_json
        from website_chunks
        where images_json is not null and images_json != '[]'
        """
    ).fetchall()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for page_url, title, raw in rows:
        try:
            images = json.loads(raw or "[]")
        except json.JSONDecodeError:
            continue
        for img in images:
            url = (img.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append((url, page_url, title or ""))
    return out


def main() -> None:
    if not DB_PATH.exists():
        log(f"No database at {DB_PATH}")
        sys.exit(1)

    settings = get_settings()
    gemini = GeminiClient(settings)
    conn = sqlite3.connect(DB_PATH)
    catalog = ImageLabelStore(conn)

    items = collect_unique_images(conn)
    already = sum(1 for url, _, _ in items if catalog.get(url))
    todo = len(items) - already
    log(f"Found {len(items)} unique images ({already} done, {todo} to label)")

    labeled = 0
    failed = 0
    for i, (img_url, page_url, title) in enumerate(items, 1):
        if catalog.get(img_url):
            continue
        log(f"[{i}/{len(items)}] {img_url[:90]}")
        try:
            label = gemini.label_image(img_url, title, page_url)
            catalog.save(img_url, label, page_url)
            catalog.commit()
            labeled += 1
            log(f"  -> {label[:120]}")
            if labeled % 25 == 0:
                n = merge_labels_into_chunks(conn)
                log(f"  (checkpoint: merged labels into {n} chunk rows so far)")
        except Exception as exc:
            failed += 1
            reject = f"REJECT: unavailable ({type(exc).__name__})"
            catalog.save(img_url, reject, page_url)
            catalog.commit()
            log(f"  !! failed: {exc} -> {reject}")
        time.sleep(0.35)

    updated = merge_labels_into_chunks(conn)
    log(f"Done. Labeled {labeled} new images ({failed} failed); updated {updated} chunk rows")


if __name__ == "__main__":
    main()
