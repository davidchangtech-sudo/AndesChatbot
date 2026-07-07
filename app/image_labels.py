from __future__ import annotations
import json
import logging
import sqlite3
from pathlib import Path

from app.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "rag.db"


class ImageLabelStore:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.execute(
            """
            create table if not exists image_catalog (
              url text primary key,
              label text not null,
              page_url text,
              rejected integer not null default 0,
              updated_at text default (datetime('now'))
            )
            """
        )

    def get(self, url: str) -> str | None:
        row = self._conn.execute("select label from image_catalog where url = ?", (url,)).fetchone()
        return row[0] if row else None

    def save(self, url: str, label: str, page_url: str) -> None:
        rejected = 1 if label.upper().startswith("REJECT") else 0
        self._conn.execute(
            """
            insert into image_catalog (url, label, page_url, rejected, updated_at)
            values (?, ?, ?, ?, datetime('now'))
            on conflict(url) do update set
              label=excluded.label,
              page_url=excluded.page_url,
              rejected=excluded.rejected,
              updated_at=excluded.updated_at
            """,
            (url, label.strip(), page_url, rejected),
        )

    def commit(self) -> None:
        self._conn.commit()


def enrich_page_images(
    gemini: GeminiClient,
    images: list[dict],
    page_title: str,
    page_url: str,
    catalog: ImageLabelStore,
    max_images: int = 4,
) -> list[dict]:
    enriched: list[dict] = []
    seen: set[str] = set()

    for img in images:
        url = (img.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)

        cached = catalog.get(url)
        if cached:
            label = cached
        else:
            try:
                label = gemini.label_image(
                    url,
                    page_title,
                    page_url,
                    img.get("alt") or "",
                    img.get("description") or img.get("caption") or "",
                )
                catalog.save(url, label, page_url)
                catalog.commit()
            except Exception as exc:
                logger.warning("Label failed %s: %s", url, exc)
                label = "REJECT: labeling failed"

        enriched.append({"url": url, "alt": img.get("alt") or "", "label": label})
        if len(enriched) >= max_images:
            break

    return enriched


def apply_labels_to_images_json(raw_json: str | None, catalog: ImageLabelStore) -> str | None:
    if not raw_json:
        return raw_json
    try:
        images = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json
    if not isinstance(images, list):
        return raw_json

    changed = False
    for img in images:
        url = img.get("url")
        if not url:
            continue
        label = catalog.get(url)
        if label and img.get("label") != label:
            img["label"] = label
            changed = True
    return json.dumps(images) if changed else raw_json


def merge_labels_into_chunks(conn: sqlite3.Connection) -> int:
    catalog = ImageLabelStore(conn)
    rows = conn.execute("select url, chunk_index, images_json from website_chunks where images_json is not null").fetchall()
    updated = 0
    for url, chunk_index, raw in rows:
        new_json = apply_labels_to_images_json(raw, catalog)
        if new_json != raw:
            conn.execute(
                "update website_chunks set images_json = ? where url = ? and chunk_index = ?",
                (new_json, url, chunk_index),
            )
            updated += 1
    conn.commit()
    return updated
