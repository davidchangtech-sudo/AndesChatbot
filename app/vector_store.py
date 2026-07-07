from __future__ import annotations
import json
from dataclasses import dataclass

from supabase import Client, create_client

from app.config import Settings


@dataclass
class RetrievedChunk:
    id: str
    url: str
    title: str | None
    content: str
    similarity: float
    images: list[dict] | None = None


def _parse_images(raw) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _normalize_chunk_row(row: dict) -> dict:
    out = dict(row)
    raw = out.get("images_json")
    if isinstance(raw, str) and raw:
        try:
            out["images_json"] = json.loads(raw)
        except json.JSONDecodeError:
            out["images_json"] = []
    elif raw is None:
        out["images_json"] = []
    return out


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    def clear_chunks(self) -> None:
        self._client.table("website_chunks").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

    def upsert_chunks(self, rows: list[dict]) -> None:
        batch_size = 50
        for i in range(0, len(rows), batch_size):
            batch = [_normalize_chunk_row(r) for r in rows[i : i + batch_size]]
            self._client.table("website_chunks").upsert(
                batch,
                on_conflict="url,chunk_index",
            ).execute()

    def search(self, query_embedding: list[float]) -> list[RetrievedChunk]:
        result = self._client.rpc(
            "match_website_chunks",
            {
                "query_embedding": query_embedding,
                "match_count": self.settings.rag_top_k,
                "match_threshold": self.settings.rag_min_similarity,
            },
        ).execute()

        chunks: list[RetrievedChunk] = []
        for row in result.data or []:
            chunks.append(
                RetrievedChunk(
                    id=str(row["id"]),
                    url=row["url"],
                    title=row.get("title"),
                    content=row["content"],
                    similarity=float(row["similarity"]),
                    images=_parse_images(row.get("images_json")),
                )
            )
        return chunks

    def save_lead(self, payload: dict) -> str:
        row = dict(payload)
        raw = row.get("conversation_json")
        if isinstance(raw, str) and raw:
            try:
                row["conversation_json"] = json.loads(raw)
            except json.JSONDecodeError:
                row["conversation_json"] = []
        result = self._client.table("chat_leads").insert(row).execute()
        if not result.data:
            raise RuntimeError("Failed to save lead")
        return str(result.data[0]["id"])

    def list_leads(self, limit: int = 100) -> list[dict]:
        result = (
            self._client.table("chat_leads")
            .select(
                "id,session_id,name,company,phone,email,topic,message,source_url,"
                "chat_summary,conversation_json,created_at"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        out: list[dict] = []
        for row in result.data or []:
            conv = row.pop("conversation_json", None) or []
            if isinstance(conv, str):
                try:
                    conv = json.loads(conv)
                except json.JSONDecodeError:
                    conv = []
            out.append(
                {
                    **row,
                    "conversation": conv,
                }
            )
        return out

    def chunk_count(self) -> int:
        result = self._client.table("website_chunks").select("id", count="exact").limit(1).execute()
        return int(result.count or 0)

    def distinct_url_count(self) -> int:
        result = self._client.table("website_chunks").select("url").limit(5000).execute()
        urls = {row["url"] for row in (result.data or [])}
        return len(urls)
