from __future__ import annotations

"""Rate limits, origin checks, and request guards for public endpoints."""

import asyncio
import hmac
import logging
import re
import time
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import Settings

logger = logging.getLogger(__name__)

SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{7,79}$")
SAFE_HTTP_URL_RE = re.compile(r"^https?://", re.I)

_chat_inflight = 0
_chat_inflight_lock = asyncio.Lock()


class SlidingWindowLimiter:
    def __init__(self, max_keys: int = 50_000) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._max_keys = max_keys

    def allow(self, key: str, limit: int, window_seconds: float) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        bucket = self._hits[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.pop(0)
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        if len(self._hits) > self._max_keys:
            self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or v[-1] < now - 3600]
        for k in stale[:10_000]:
            self._hits.pop(k, None)


_limiter = SlidingWindowLimiter()


def safe_secret_eq(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def get_client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def _origin_host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return urlparse(value.strip()).netloc.lower().replace("www.", "")
    except Exception:
        return None


def _allowed_hosts(settings: Settings) -> set[str]:
    hosts: set[str] = set()
    for origin in settings.origin_list:
        h = _origin_host(origin)
        if h:
            hosts.add(h)
            hosts.add(h.replace("www.", ""))
    return hosts


def check_browser_origin(request: Request, settings: Settings) -> None:
    if not settings.require_browser_origin_effective:
        return
    allowed = _allowed_hosts(settings)
    if not allowed:
        return
    origin = _origin_host(request.headers.get("origin"))
    referer = _origin_host(request.headers.get("referer"))
    if origin and origin.replace("www.", "") in {h.replace("www.", "") for h in allowed}:
        return
    if referer and referer.replace("www.", "") in {h.replace("www.", "") for h in allowed}:
        return
    logger.warning("Blocked request: origin=%s referer=%s ip=%s", origin, referer, get_client_ip(request, settings))
    raise HTTPException(status_code=403, detail="Forbidden")


def check_honeypot(value: str | None) -> None:
    if value and value.strip():
        raise HTTPException(status_code=400, detail="Invalid request")


def validate_session_id(session_id: str | None) -> None:
    if session_id is None:
        return
    if not SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session")


def validate_source_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if len(url) > 500:
        raise HTTPException(status_code=400, detail="Invalid source URL")
    if not SAFE_HTTP_URL_RE.match(url):
        raise HTTPException(status_code=400, detail="Invalid source URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid source URL")
    return url


def enforce_rate_limit(request: Request, settings: Settings, scope: str, limit: int, window_seconds: float) -> None:
    ip = get_client_ip(request, settings)
    key = f"{scope}:{ip}"
    if not _limiter.allow(key, limit, window_seconds):
        logger.warning("Rate limit exceeded: scope=%s ip=%s", scope, ip)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(int(window_seconds))},
        )


def enforce_global_rate_limit(request: Request, settings: Settings) -> None:
    enforce_rate_limit(
        request,
        settings,
        "global",
        settings.rate_limit_global_per_minute,
        60.0,
    )


def enforce_chat_rate_limits(request: Request, settings: Settings) -> None:
    enforce_global_rate_limit(request, settings)
    enforce_rate_limit(request, settings, "chat_min", settings.rate_limit_chat_per_minute, 60.0)
    enforce_rate_limit(request, settings, "chat_hour", settings.rate_limit_chat_per_hour, 3600.0)


def enforce_leads_rate_limits(request: Request, settings: Settings) -> None:
    enforce_global_rate_limit(request, settings)
    enforce_rate_limit(request, settings, "leads_hour", settings.rate_limit_leads_per_hour, 3600.0)
    if settings.rate_limit_leads_per_day > 0:
        enforce_rate_limit(request, settings, "leads_day", settings.rate_limit_leads_per_day, 86400.0)


async def chat_inflight_enter(settings: Settings) -> None:
    global _chat_inflight
    async with _chat_inflight_lock:
        if _chat_inflight >= settings.max_inflight_chat:
            raise HTTPException(status_code=503, detail="Server busy. Try again shortly.")
        _chat_inflight += 1


async def chat_inflight_exit() -> None:
    global _chat_inflight
    async with _chat_inflight_lock:
        _chat_inflight = max(0, _chat_inflight - 1)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        if request.url.path.startswith("/api/") or request.url.path in ("/chat", "/leads"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            raw = request.headers.get("content-length")
            if raw:
                try:
                    if int(raw) > self.max_bytes:
                        return JSONResponse(status_code=413, content={"detail": "Request too large"})
                except ValueError:
                    return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        return await call_next(request)
