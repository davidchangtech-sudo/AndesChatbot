from __future__ import annotations
import asyncio
import os
import time

import certifi
import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AndesChatbotIndexer/1.0; "
        "+https://www.andestech.com; authorized knowledge-base indexer)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DEFAULT_TIMEOUT = 60.0
RETRY_STATUS = {429, 502, 503, 504}

_throttle_delay = 2.5
_wordfence_cooldown = 120.0
_throttle_lock = asyncio.Lock()
_last_request_at = 0.0


def configure_crawl(delay_seconds: float, wordfence_cooldown: float = 120.0) -> None:
    global _throttle_delay, _wordfence_cooldown
    _throttle_delay = max(delay_seconds, 0.15)
    _wordfence_cooldown = max(wordfence_cooldown, 15.0)


def _ssl_verify():
    if os.getenv("HTTP_SSL_VERIFY", "true").lower() in ("0", "false", "no"):
        return False
    return certifi.where()


def async_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        verify=_ssl_verify(),
        follow_redirects=True,
    )


async def _throttle() -> None:
    global _last_request_at
    async with _throttle_lock:
        now = time.monotonic()
        wait = _throttle_delay - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


def _is_wordfence_block(resp: httpx.Response) -> bool:
    body = (resp.text or "").lower()
    return "wordfence" in body or "blocked" in body and "requests per minute" in body


async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_attempts: int = 6,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        await _throttle()
        try:
            resp = await client.get(url)
            if resp.status_code in RETRY_STATUS and attempt < max_attempts - 1:
                if _is_wordfence_block(resp) or resp.status_code == 503:
                    wait = _wordfence_cooldown
                else:
                    wait = min(2**attempt, 30)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                await asyncio.sleep(min(2**attempt, 30))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Failed to fetch {url}")
