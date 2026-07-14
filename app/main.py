from __future__ import annotations
import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.chat_service import ChatService
from app.config import Settings, get_settings
from app.lead_utils import build_lead_needs_summary, conversation_to_json
from app.site_links import QUICK_LINKS
from app.models import ChatRequest, ChatResponse, LeadRecord, LeadRequest, LeadResponse, LeadStatusUpdate, ReindexResponse
from app.reindex import run_reindex
from app.security import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    chat_inflight_enter,
    chat_inflight_exit,
    check_browser_origin,
    enforce_chat_rate_limits,
    enforce_leads_rate_limits,
    safe_secret_eq,
    validate_session_id,
    validate_source_url,
)
from app.store import get_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store(settings)
    mode = "local" if store.__class__.__name__ == "LocalVectorStore" else "supabase"
    chunks = getattr(store, "chunk_count", lambda: "?")()
    logger.info("Andes chatbot API started (storage=%s, chunks=%s)", mode, chunks)
    yield


app = FastAPI(
    title="Andes Technology Chatbot API",
    description="RAG chatbot for https://www.andestech.com/en/",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
_cors_kwargs: dict = {
    "allow_origins": settings.origin_list,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "X-Cron-Secret", "X-Lead-Admin-Secret", "Authorization"],
}
# Local LAN testing: allow private-network hosts when dev routes are enabled
if settings.enable_dev_routes:
    _cors_kwargs["allow_origin_regex"] = (
        r"https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?"
    )
app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)


def verify_cron_secret(
    x_cron_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    token = x_cron_secret
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if not safe_secret_eq(token, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


def verify_lead_admin_secret(
    x_lead_admin_secret: str | None = Header(default=None, alias="X-Lead-Admin-Secret"),
) -> None:
    if not safe_secret_eq(x_lead_admin_secret, settings.effective_lead_admin_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _generic_error(status: int = 500) -> HTTPException:
    return HTTPException(status_code=status, detail="Request failed. Please try again later.")


@app.get("/health")
async def health() -> dict:
    store = get_store(settings)
    chunks = getattr(store, "chunk_count", lambda: 0)()
    urls = getattr(store, "distinct_url_count", lambda: None)()
    return {
        "status": "ok",
        "service": "andes-chatbot",
        "kb_chunks": chunks,
        "kb_urls": urls,
        "kb_mode": "offline_catalog" if chunks and chunks < 200 else "indexed",
    }


@app.get("/site-links")
async def site_links() -> dict:
    return {"links": QUICK_LINKS}


@app.get("/api/kb-status")
async def kb_status(_: None = Depends(verify_cron_secret)) -> dict:
    """How much of the site is in the knowledge base (requires CRON_SECRET)."""
    store = get_store(settings)
    chunks = getattr(store, "chunk_count", lambda: 0)()
    urls = getattr(store, "distinct_url_count", lambda: None)()
    return {
        "chunks": chunks,
        "distinct_urls": urls,
        "max_crawl_pages": settings.max_crawl_pages,
        "crawl_base_url": settings.crawl_base_url,
        "note": "Run POST /reindex when Wordfence allows crawls. Local dev may use scripts/seed_kb.py.",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    enforce_chat_rate_limits(request, settings)
    check_browser_origin(request, settings)
    validate_session_id(req.session_id)

    await chat_inflight_enter(settings)
    try:
        service = ChatService(settings)
        return await asyncio.wait_for(
            asyncio.to_thread(service.handle, req),
            timeout=settings.chat_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("Chat timed out ip=%s", request.client)
        raise _generic_error(503) from None
    finally:
        await chat_inflight_exit()


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    enforce_chat_rate_limits(request, settings)
    check_browser_origin(request, settings)
    validate_session_id(req.session_id)

    await chat_inflight_enter(settings)

    async def ndjson_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        error_holder: list[BaseException] = []

        def worker() -> None:
            try:
                service = ChatService(settings)
                for event in service.stream(req):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except BaseException as exc:
                error_holder.append(exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=settings.chat_timeout_seconds)
                except asyncio.TimeoutError:
                    logger.warning("Chat stream timed out ip=%s", request.client)
                    yield json.dumps({"type": "error", "detail": "timeout"}) + "\n"
                    break
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
            if error_holder:
                logger.exception("Chat stream failed", exc_info=error_holder[0])
                yield json.dumps({"type": "error", "detail": "Request failed"}) + "\n"
        finally:
            await chat_inflight_exit()

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/leads", response_model=LeadResponse)
async def submit_lead(req: LeadRequest, request: Request) -> LeadResponse:
    enforce_leads_rate_limits(request, settings)
    check_browser_origin(request, settings)
    validate_session_id(req.session_id)
    source_url = validate_source_url(req.source_url)

    chat_summary = await asyncio.to_thread(
        build_lead_needs_summary,
        req.conversation,
        settings,
        name=req.name,
        company=req.company,
        topic=req.topic,
        message=req.message,
    )
    store = get_store(settings)
    try:
        lead_id = store.save_lead(
            {
                "session_id": req.session_id,
                "name": req.name,
                "company": req.company,
                "phone": req.phone,
                "email": str(req.email),
                "topic": req.topic,
                "message": req.message,
                "source_url": source_url,
                "chat_summary": chat_summary,
                "conversation_json": conversation_to_json(req.conversation),
            }
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to save lead")
        raise _generic_error() from None
    return LeadResponse(lead_id=lead_id, chat_summary=chat_summary)


@app.get("/admin/leads", response_model=list[LeadRecord])
async def list_leads(
    _: None = Depends(verify_lead_admin_secret),
    limit: int = 100,
    tab: str = "active",
) -> list[LeadRecord]:
    store = get_store(settings)
    if not hasattr(store, "list_leads"):
        raise HTTPException(status_code=501, detail="Not available")
    rows = store.list_leads(limit=min(limit, 200), tab=tab)
    return [LeadRecord.model_validate(r) for r in rows]


@app.patch("/admin/leads/{lead_id}", response_model=LeadRecord)
async def update_lead_status(
    lead_id: str,
    body: LeadStatusUpdate,
    _: None = Depends(verify_lead_admin_secret),
) -> LeadRecord:
    store = get_store(settings)
    if not hasattr(store, "update_lead_status"):
        raise HTTPException(status_code=501, detail="Not available")
    ok = store.update_lead_status(lead_id, body.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    rows = store.list_leads(limit=200, tab="all")
    match = next((r for r in rows if r["id"] == lead_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadRecord.model_validate(match)


@app.get("/admin")
async def admin_leads_page() -> FileResponse:
    return FileResponse("static/admin-leads.html", media_type="text/html")


@app.post("/reindex", response_model=ReindexResponse)
async def reindex(_: None = Depends(verify_cron_secret)) -> ReindexResponse:
    try:
        result = await run_reindex(settings)
        return ReindexResponse(
            ok=result["ok"],
            pages_crawled=result["pages_crawled"],
            chunks_stored=result["chunks_stored"],
            message=result["message"],
        )
    except Exception:
        logger.exception("Reindex failed")
        raise _generic_error() from None


@app.get("/api/crawl-progress/stream")
async def crawl_progress_stream() -> StreamingResponse:
    import json

    async def event_gen():
        while True:
            from app.crawl_progress import read_progress

            prog = read_progress()
            store = get_store(settings)
            prog["kb_chunks"] = getattr(store, "chunk_count", lambda: 0)()
            prog["kb_urls"] = getattr(store, "distinct_url_count", lambda: None)()
            yield f"data: {json.dumps(prog)}\n\n"
            # Stop streaming once crawl is finished so the UI tick does not keep running.
            if (prog.get("status") or "").lower() in ("done", "failed", "idle"):
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/crawl-progress")
async def crawl_progress_api() -> JSONResponse:
    from app.crawl_progress import read_progress

    prog = read_progress()
    store = get_store(settings)
    prog["kb_chunks"] = getattr(store, "chunk_count", lambda: 0)()
    prog["kb_urls"] = getattr(store, "distinct_url_count", lambda: None)()
    return JSONResponse(
        content=prog,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/crawl-progress")
async def crawl_progress_page() -> FileResponse:
    if not settings.dev_routes_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        "static/crawl-progress.html",
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/test")
async def test_page() -> FileResponse:
    if not settings.dev_routes_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("static/test.html", media_type="text/html")


@app.get("/wordpress")
async def wordpress_sample_page() -> FileResponse:
    if not settings.dev_routes_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("local-wordpress/index.html", media_type="text/html")


@app.get("/widget.js")
async def widget_js() -> FileResponse:
    return FileResponse(
        "static/widget.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )


static_dir = __import__("pathlib").Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid request"})


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    if settings.is_production:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return JSONResponse(status_code=500, content={"detail": str(exc)})
