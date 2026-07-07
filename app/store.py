from __future__ import annotations
from app.config import Settings
from app.local_store import LocalVectorStore
from app.vector_store import VectorStore


def _use_local_storage(settings: Settings) -> bool:
    explicit = getattr(settings, "rag_storage", "auto")
    if explicit == "local":
        return True
    if explicit == "supabase":
        return False
    return (
        "your-project" in settings.supabase_url
        or settings.supabase_service_role_key.startswith("your_")
    )


def get_store(settings: Settings):
    if _use_local_storage(settings):
        return LocalVectorStore(settings)
    return VectorStore(settings)
