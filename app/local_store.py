from __future__ import annotations
import json
import math
import sqlite3
import uuid
from pathlib import Path

from app.config import Settings
from app.image_labels import ImageLabelStore
from app.images import normalize_image_record
from app.hybrid_search import extract_search_tokens, keyword_score_row
from app.vector_store import RetrievedChunk, _parse_images

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "rag.db"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LocalVectorStore:
    """SQLite-backed store for local dev when Supabase is not configured."""

    def __init__(self, settings: Settings):
        self.settings = settings
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            create table if not exists website_chunks (
              id text primary key,
              url text not null,
              title text,
              content text not null,
              word_count int not null default 0,
              chunk_index int not null default 0,
              embedding text not null,
              images_json text,
              updated_at text,
              unique (url, chunk_index)
            );
            create table if not exists chat_leads (
              id text primary key,
              session_id text,
              name text not null,
              company text,
              phone text,
              email text not null,
              topic text,
              message text not null,
              source_url text,
              chat_summary text,
              conversation_json text,
              created_at text default (datetime('now'))
            );
            """
        )
        self._migrate_leads_schema()
        self._conn.commit()

    def _migrate_leads_schema(self) -> None:
        cols = {row[1] for row in self._conn.execute("pragma table_info(chat_leads)")}
        if "chat_summary" not in cols:
            self._conn.execute("alter table chat_leads add column chat_summary text")
        if "conversation_json" not in cols:
            self._conn.execute("alter table chat_leads add column conversation_json text")
        if "phone" not in cols:
            self._conn.execute("alter table chat_leads add column phone text")
        if "status" not in cols:
            self._conn.execute("alter table chat_leads add column status text not null default 'new'")
        chunk_cols = {row[1] for row in self._conn.execute("pragma table_info(website_chunks)")}
        if "images_json" not in chunk_cols:
            self._conn.execute("alter table website_chunks add column images_json text")

    def clear_chunks(self) -> None:
        self._conn.execute("delete from website_chunks")
        self._conn.commit()

    def indexed_urls(self) -> set[str]:
        rows = self._conn.execute("select distinct url from website_chunks").fetchall()
        return {row[0] for row in rows}

    def upsert_chunks(self, rows: list[dict]) -> None:
        for row in rows:
            chunk_id = str(uuid.uuid4())
            self._conn.execute(
                """
                insert into website_chunks (
                  id, url, title, content, word_count, chunk_index, embedding, images_json, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(url, chunk_index) do update set
                  title=excluded.title,
                  content=excluded.content,
                  word_count=excluded.word_count,
                  embedding=excluded.embedding,
                  images_json=excluded.images_json,
                  updated_at=excluded.updated_at
                """,
                (
                    chunk_id,
                    row["url"],
                    row.get("title"),
                    row["content"],
                    row.get("word_count", 0),
                    row["chunk_index"],
                    json.dumps(row["embedding"]),
                    row.get("images_json"),
                    row.get("updated_at"),
                ),
            )
        self._conn.commit()

    def _enrich_images(self, images: list[dict]) -> list[dict]:
        catalog = ImageLabelStore(self._conn)
        enriched: list[dict] = []
        for img in images:
            rec = normalize_image_record(img)
            cached = catalog.get(rec["url"])
            if cached and not rec.get("label"):
                rec["label"] = cached
            enriched.append(normalize_image_record(rec))
        return enriched

    def search_by_url_markers(self, markers: tuple[str, ...], max_chunks: int = 6) -> list[RetrievedChunk]:
        """Fast path: load chunks by canonical product URL without embedding API."""
        best_per_url: dict[str, sqlite3.Row] = {}
        for marker in markers:
            rows = self._conn.execute(
                """
                select id, url, title, content, images_json, chunk_index
                from website_chunks
                where lower(url) like ?
                order by chunk_index asc
                """,
                (f"%{marker.lower()}%",),
            ).fetchall()
            for row in rows:
                url = row["url"]
                prev = best_per_url.get(url)
                if prev is None or row["chunk_index"] < prev["chunk_index"]:
                    best_per_url[url] = row

        out: list[RetrievedChunk] = []
        for row in best_per_url.values():
            out.append(
                RetrievedChunk(
                    id=row["id"],
                    url=row["url"],
                    title=row["title"],
                    content=row["content"],
                    similarity=0.9,
                    images=_parse_images(row["images_json"]),
                )
            )
            if len(out) >= max_chunks:
                break

        for chunk in out:
            chunk.images = self._enrich_images(chunk.images or [])
        return out

    def search_by_page_path(self, page_path: str, max_chunks: int = 6) -> list[RetrievedChunk]:
        path = (page_path or "").strip().rstrip("/").lower()
        if not path or path == "/":
            return []
        rows = self._conn.execute(
            """
            select id, url, title, content, images_json, chunk_index
            from website_chunks
            where lower(url) like ?
            order by chunk_index asc
            limit ?
            """,
            (f"%{path}%", max_chunks * 3),
        ).fetchall()
        out: list[RetrievedChunk] = []
        seen_urls: set[str] = set()
        for row in rows:
            url = row["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            out.append(
                RetrievedChunk(
                    id=row["id"],
                    url=url,
                    title=row["title"],
                    content=row["content"],
                    similarity=0.88,
                    images=_parse_images(row["images_json"]),
                )
            )
            if len(out) >= max_chunks:
                break
        for chunk in out:
            chunk.images = self._enrich_images(chunk.images or [])
        return out

    def search_keywords(self, query: str, *, limit: int = 8) -> list[RetrievedChunk]:
        tokens = extract_search_tokens(query)
        if not tokens:
            return []

        rows = self._conn.execute(
            "select id, url, title, content, images_json from website_chunks"
        ).fetchall()
        scored: list[RetrievedChunk] = []
        for row in rows:
            lexical = keyword_score_row(row["title"], row["content"], tokens)
            if lexical < 2.0:
                continue
            sim = min(0.92, 0.44 + lexical * 0.04)
            scored.append(
                RetrievedChunk(
                    id=row["id"],
                    url=row["url"],
                    title=row["title"],
                    content=row["content"],
                    similarity=sim,
                    images=_parse_images(row["images_json"]),
                )
            )
        scored.sort(key=lambda c: c.similarity, reverse=True)
        top = scored[:limit]
        for chunk in top:
            chunk.images = self._enrich_images(chunk.images or [])
        return top

    def search(self, query_embedding: list[float]) -> list[RetrievedChunk]:
        rows = self._conn.execute(
            "select id, url, title, content, embedding, images_json from website_chunks"
        ).fetchall()

        scored: list[RetrievedChunk] = []
        for row in rows:
            emb = json.loads(row["embedding"])
            sim = _cosine_similarity(query_embedding, emb)
            if sim >= self.settings.rag_min_similarity:
                scored.append(
                    RetrievedChunk(
                        id=row["id"],
                        url=row["url"],
                        title=row["title"],
                        content=row["content"],
                        similarity=sim,
                        images=_parse_images(row["images_json"]),
                    )
                )

        scored.sort(key=lambda c: c.similarity, reverse=True)
        top = scored[: self.settings.rag_top_k]
        for chunk in top:
            chunk.images = self._enrich_images(chunk.images or [])
        return top

    def save_lead(self, payload: dict) -> str:
        lead_id = str(uuid.uuid4())
        self._conn.execute(
            """
            insert into chat_leads (
              id, session_id, name, company, phone, email, topic, message, source_url,
              chat_summary, conversation_json, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                payload.get("session_id"),
                payload["name"],
                payload.get("company"),
                payload.get("phone"),
                payload["email"],
                payload.get("topic"),
                payload["message"],
                payload.get("source_url"),
                payload.get("chat_summary"),
                payload.get("conversation_json"),
                payload.get("status") or "new",
            ),
        )
        self._conn.commit()
        return lead_id

    def list_leads(self, limit: int = 100, tab: str = "active") -> list[dict]:
        tab = (tab or "active").lower()
        if tab == "archived":
            where = "where status = 'finished'"
            order = "order by created_at desc"
        elif tab == "all":
            where = ""
            order = """
              order by
                case status when 'new' then 0 when 'emailed' then 1 when 'finished' then 2 else 1 end,
                created_at desc
            """
        else:
            where = "where status in ('new', 'emailed')"
            order = """
              order by
                case status when 'new' then 0 when 'emailed' then 1 else 2 end,
                created_at desc
            """
        rows = self._conn.execute(
            f"""
            select id, session_id, name, company, phone, email, topic, message, source_url,
                   chat_summary, conversation_json, created_at, status
            from chat_leads
            {where}
            {order}
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [self._lead_row_to_dict(r) for r in rows]

    def update_lead_status(self, lead_id: str, status: str) -> bool:
        if status not in ("new", "emailed", "finished"):
            return False
        cur = self._conn.execute(
            "update chat_leads set status = ? where id = ?",
            (status, lead_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _lead_row_to_dict(row: sqlite3.Row) -> dict:
        conv: list[dict] = []
        raw = row["conversation_json"]
        if raw:
            try:
                conv = json.loads(raw)
            except json.JSONDecodeError:
                conv = []
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "name": row["name"],
            "company": row["company"],
            "phone": row["phone"],
            "email": row["email"],
            "topic": row["topic"],
            "message": row["message"],
            "source_url": row["source_url"],
            "chat_summary": row["chat_summary"],
            "conversation": conv,
            "created_at": row["created_at"],
            "status": row["status"] if "status" in row.keys() else "new",
        }

    def chunk_count(self) -> int:
        row = self._conn.execute("select count(*) as c from website_chunks").fetchone()
        return int(row["c"]) if row else 0

    def distinct_url_count(self) -> int:
        row = self._conn.execute("select count(distinct url) as c from website_chunks").fetchone()
        return int(row["c"]) if row else 0
