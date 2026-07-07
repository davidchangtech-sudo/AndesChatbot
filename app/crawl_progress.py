from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

PROGRESS_FILE = Path(__file__).resolve().parent.parent / "data" / "crawl_progress.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_progress(
    *,
    status: str,
    total_urls: int = 0,
    pages_indexed: int = 0,
    chunks_stored: int = 0,
    current_url: str | None = None,
    message: str | None = None,
) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if PROGRESS_FILE.exists():
        try:
            existing = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    payload = {
        "status": status,
        "total_urls": total_urls,
        "pages_indexed": pages_indexed,
        "chunks_stored": chunks_stored,
        "current_url": current_url,
        "message": message,
        "started_at": existing.get("started_at") if status == "running" and existing.get("status") == "running" else _now(),
        "updated_at": _now(),
    }
    if status in ("done", "failed", "idle"):
        payload["finished_at"] = _now()
    PROGRESS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {
            "status": "idle",
            "total_urls": 0,
            "pages_indexed": 0,
            "chunks_stored": 0,
            "percent": 0,
            "current_url": None,
            "message": "No crawl in progress",
        }
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "idle", "total_urls": 0, "pages_indexed": 0, "chunks_stored": 0, "percent": 0}
    total = int(data.get("total_urls") or 0)
    done = int(data.get("pages_indexed") or 0)
    data["percent"] = round(100 * done / total, 1) if total else 0
    return data
