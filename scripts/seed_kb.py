#!/usr/bin/env python3
"""Load seed_chunks.json into the local knowledge base (no website crawl)."""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SEED_FILE = ROOT / "data" / "seed_chunks.json"


async def main() -> int:
    from app.config import get_settings
    from app.gemini_client import GeminiClient
    from app.reindex import _embed_with_retry
    from app.store import get_store

    if not SEED_FILE.exists():
        print(f"Missing {SEED_FILE}", file=sys.stderr)
        return 1

    seeds = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    settings = get_settings()
    gemini = GeminiClient(settings)
    store = get_store(settings)

    from app.chunker import TextChunk, chunk_text

    rows: list[dict] = []
    url_chunk_counter: dict[str, int] = {}
    for item in seeds:
        pieces = chunk_text(item["content"], min_words=80, max_words=220)
        if not pieces:
            wc = len(item["content"].split())
            pieces = [TextChunk(content=item["content"], word_count=wc, chunk_index=0)]
        for piece in pieces:
            url = item["url"]
            chunk_index = url_chunk_counter.get(url, 0)
            url_chunk_counter[url] = chunk_index + 1
            embedding = await _embed_with_retry(gemini, piece.content, url, chunk_index)
            if embedding is None:
                print(f"Failed to embed: {url} #{chunk_index}", file=sys.stderr)
                continue
            images = item.get("images") or []
            rows.append(
                {
                    "url": url,
                    "title": item["title"],
                    "content": piece.content,
                    "word_count": piece.word_count,
                    "chunk_index": chunk_index,
                    "embedding": embedding,
                    "images_json": json.dumps(images) if images else None,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await asyncio.sleep(1.2)

    if not rows:
        print("No chunks seeded.", file=sys.stderr)
        return 1

    store.clear_chunks()
    store.upsert_chunks(rows)
    print(f"Seeded {len(rows)} chunks from {SEED_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
