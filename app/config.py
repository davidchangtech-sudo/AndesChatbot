from __future__ import annotations
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8000
    public_api_url: str = "http://localhost:8000"
    allowed_origins: str = "https://www.andestech.com,https://andestech.com"

    google_api_key: str
    gemini_chat_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    supabase_url: str = "https://your-project.supabase.co"
    supabase_service_role_key: str = "your_service_role_key"
    supabase_db_url: str | None = None
    rag_storage: str = "auto"  # auto | local | supabase
    local_rag_db_path: str | None = None

    crawl_base_url: str = "https://www.andestech.com/en/"
    sitemap_urls: str = (
        "https://www.andestech.com/sitemap.xml,"
        "https://www.andestech.com/sitemap_index.xml,"
        "http://www.andestech.com/sitemap_index.xml"
    )
    max_crawl_pages: int = 2000
    crawl_delay_seconds: float = 2.5
    crawl_concurrency: int = 1
    sitemap_concurrency: int = 1
    crawl_wordfence_cooldown: float = 120.0
    rag_top_k: int = 4
    rag_min_similarity: float = 0.42
    enable_gemini_fallback: bool = True
    rag_fallback_max_similarity: float = 0.56
    enable_hybrid_search: bool = True
    page_url_boost: float = 0.18

    cron_secret: str
    lead_admin_secret: str | None = None
    lead_notify_email: str | None = None

    # Security / abuse protection (tune per traffic)
    enable_dev_routes: bool | None = None
    require_browser_origin: bool | None = None
    trust_proxy_headers: bool = True
    max_request_body_bytes: int = 32_768
    rate_limit_global_per_minute: int = 120
    rate_limit_chat_per_minute: int = 12
    rate_limit_chat_per_hour: int = 80
    rate_limit_leads_per_hour: int = 5
    rate_limit_leads_per_day: int = 20
    max_inflight_chat: int = 25
    chat_timeout_seconds: float = 120.0

    @property
    def is_production(self) -> bool:
        url = self.public_api_url.lower()
        return not (url.startswith("http://localhost") or url.startswith("http://127.0.0.1"))

    @property
    def dev_routes_enabled(self) -> bool:
        if self.enable_dev_routes is not None:
            return self.enable_dev_routes
        return not self.is_production

    @property
    def require_browser_origin_effective(self) -> bool:
        if self.require_browser_origin is not None:
            return self.require_browser_origin
        return self.is_production

    @property
    def effective_lead_admin_secret(self) -> str:
        return (self.lead_admin_secret or self.cron_secret).strip()

    @property
    def origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sitemap_url_list(self) -> list[str]:
        return [u.strip() for u in self.sitemap_urls.split(",") if u.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
