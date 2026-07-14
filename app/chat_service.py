from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from app.competitor_guard import (
    filter_competitor_chunks,
    is_competitor_question,
    localized_competitor_decline,
    strip_competitor_sentences,
)
from app.chat_tuning import PromptProfile, prompt_profile
from app.config import Settings
from app.conversation_summary import update_conversation_summary
from app.fallback_chat import (
    FALLBACK_SYSTEM_PROMPT,
    NO_ANSWER_REPLY,
    OUT_OF_SCOPE_REPLY,
    localized_no_answer,
    localized_out_of_scope,
    build_fallback_user_prompt,
    classify_andes_relevance,
    filter_fallback_reply,
    should_use_fallback,
)
from app.gemini_client import GeminiClient
from app.models import ChatMessage, ChatRequest, ChatResponse, ReadMoreLink
from app.offline_faq import instant_reply, offline_keyword_reply
from app.prompts import (
    LEAD_INTENT_KEYWORDS,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_LITE,
    build_context_block,
    build_user_prompt,
    clean_reply_citations,
    clamp_reply_brevity,
)
from app.hybrid_search import merge_hybrid_chunks
from app.retrieval import (
    NAMED_PRODUCT_SLUGS,
    _named_products_in_text,
    dedupe_chunks_by_url,
    normalize_page_path,
    rerank_chunks,
    resolve_search_query,
)
from app.site_links import (
    QUICK_LINKS,
    READ_MORE_MIN_QUESTION_CHARS,
    READ_MORE_MIN_SIMILARITY,
    SITE_BASE,
    SMALLTALK,
)
from app.store import get_store

UNCERTAIN_PHRASES = (
    "not sure",
    "don't know",
    "do not know",
    "cannot find",
    "can't find",
    "no information",
    "contact andes",
    "contacting andes",
    "insufficient",
)


@dataclass
class _Prepared:
    question: str
    user_prompt: str
    search_query: str
    chunks: list
    suggest_lead: bool
    prior_summary: str | None
    history: list[ChatMessage]
    profile: PromptProfile
    mode: str = "rag"  # rag | fallback
    page_url: str | None = None


class ChatService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gemini = GeminiClient(settings)
        self.store = get_store(settings)

    def _retrieve_chunks(
        self,
        *,
        question: str,
        search_query: str,
        profile: PromptProfile,
        history: list[ChatMessage],
        page_url: str | None,
    ) -> list:
        page_path = normalize_page_path(page_url)
        rerank = lambda chunks: rerank_chunks(
            chunks,
            search_query,
            page_url=page_url,
            page_boost=self.settings.page_url_boost,
        )

        if page_path and hasattr(self.store, "search_by_page_path"):
            page_chunks = self.store.search_by_page_path(page_path, max_chunks=profile.chunk_count)
            if page_chunks:
                return dedupe_chunks_by_url(rerank(page_chunks))[: profile.chunk_count]

        chunks: list = []
        if profile.use_lite_prompt and not history and hasattr(self.store, "search_by_url_markers"):
            products = _named_products_in_text(question)
            markers: tuple[str, ...] = ()
            for product in products:
                markers = NAMED_PRODUCT_SLUGS.get(product, ())
                if markers:
                    break
            if markers:
                chunks = dedupe_chunks_by_url(
                    rerank(self.store.search_by_url_markers(markers))
                )[: profile.chunk_count]

        if chunks:
            return chunks

        query_embedding = self.gemini.embed_query(search_query)
        vector_chunks = self.store.search(query_embedding)
        if self.settings.enable_hybrid_search and hasattr(self.store, "search_keywords"):
            keyword_chunks = self.store.search_keywords(
                search_query,
                limit=max(profile.chunk_count * 2, 8),
            )
            merged = merge_hybrid_chunks(
                vector_chunks,
                keyword_chunks,
                limit=max(profile.chunk_count * 2, 8),
            )
        else:
            merged = vector_chunks

        return dedupe_chunks_by_url(rerank(merged))[: profile.chunk_count]

    def _prepare(self, req: ChatRequest) -> ChatResponse | _Prepared:
        question = req.message.strip()
        page_url = (req.page_url or "").strip() or None
        keyword_lead = _suggests_lead_form(question)

        quick = instant_reply(question)
        if quick:
            return ChatResponse(
                reply=quick,
                sources=[],
                read_more=None,
                suggest_lead_form=keyword_lead,
                show_lead_cta=False,
                uncertain=False,
                answer_mode="instant",
            )

        if is_competitor_question(question):
            return ChatResponse(
                reply=localized_competitor_decline(question),
                sources=[],
                read_more=None,
                suggest_lead_form=keyword_lead,
                show_lead_cta=False,
                uncertain=False,
                answer_mode="declined",
            )

        kb_size = getattr(self.store, "chunk_count", lambda: 0)()
        offline = offline_keyword_reply(question) if kb_size < 80 else None
        if offline:
            return ChatResponse(
                reply=offline,
                sources=[],
                read_more=_fallback_read_more(question),
                suggest_lead_form=keyword_lead,
                show_lead_cta=False,
                uncertain=False,
                answer_mode="offline",
            )

        profile = prompt_profile(
            question,
            history_len=len(req.history),
            has_summary=bool((req.conversation_summary or "").strip()),
        )

        search_query = resolve_search_query(
            question,
            req.history,
            req.conversation_summary,
        )

        chunks: list = self._retrieve_chunks(
            question=question,
            search_query=search_query,
            profile=profile,
            history=req.history,
            page_url=page_url,
        )
        chunks = filter_competitor_chunks(chunks)

        if not chunks:
            return self._no_kb_response(req, question, keyword_lead, page_url=page_url)

        use_fallback = (
            self.settings.enable_gemini_fallback
            and should_use_fallback(chunks, max_similarity=self.settings.rag_fallback_max_similarity)
        )

        suggest_lead = _should_suggest_lead(
            req,
            question,
            keyword_lead=keyword_lead,
            uncertain=use_fallback,
            mode="fallback" if use_fallback else "rag",
        )

        if use_fallback:
            return self._prepare_fallback(
                req,
                question=question,
                suggest_lead=suggest_lead,
                search_query=search_query,
                chunks=chunks,
                profile=profile,
                page_url=page_url,
                weak_context=build_context_block(chunks[:2], 500)
                if chunks
                else "",
            )

        context = build_context_block(
            chunks,
            profile.max_chunk_chars,
        )
        user_prompt = build_user_prompt(
            question,
            context,
            req.history,
            req.conversation_summary,
            lite=profile.use_lite_prompt,
        )
        return _Prepared(
            question=question,
            user_prompt=user_prompt,
            search_query=search_query,
            chunks=chunks,
            suggest_lead=suggest_lead,
            prior_summary=req.conversation_summary,
            history=req.history,
            profile=profile,
            page_url=page_url,
        )

    def _weak_context(self, prepared: _Prepared, *, max_chars: int = 600) -> str:
        if not prepared.chunks:
            return ""
        return build_context_block(prepared.chunks[:2], max_chars)

    def _prepare_fallback(
        self,
        req: ChatRequest,
        *,
        question: str,
        suggest_lead: bool,
        search_query: str,
        chunks: list,
        profile: PromptProfile,
        weak_context: str = "",
        page_url: str | None = None,
    ) -> ChatResponse | _Prepared:
        if not self.settings.enable_gemini_fallback:
            return ChatResponse(
                reply=localized_no_answer(question),
                sources=[],
                read_more=_fallback_read_more(question),
                suggest_lead_form=suggest_lead or True,
                show_lead_cta=False,
                uncertain=True,
                answer_mode="no_kb",
                conversation_summary=req.conversation_summary,
            )

        relevance = classify_andes_relevance(
            self.gemini,
            question,
            history=req.history,
            conversation_summary=req.conversation_summary,
        )
        if relevance != "related":
            return ChatResponse(
                reply=localized_out_of_scope(question),
                sources=[],
                read_more=_fallback_read_more(question),
                suggest_lead_form=False,
                show_lead_cta=False,
                uncertain=True,
                answer_mode="declined",
                conversation_summary=req.conversation_summary,
            )

        return _Prepared(
            question=question,
            user_prompt=build_fallback_user_prompt(
                question,
                history=req.history,
                conversation_summary=req.conversation_summary,
                weak_context=weak_context,
            ),
            search_query=search_query,
            chunks=chunks,
            suggest_lead=suggest_lead or True,
            prior_summary=req.conversation_summary,
            history=req.history,
            profile=profile,
            mode="fallback",
            page_url=page_url,
        )

    def _no_kb_response(
        self, req: ChatRequest, question: str, keyword_lead: bool, *, page_url: str | None = None
    ) -> ChatResponse | _Prepared:
        profile = prompt_profile(
            question,
            history_len=len(req.history),
            has_summary=bool((req.conversation_summary or "").strip()),
        )
        suggest_lead = _should_suggest_lead(
            req,
            question,
            keyword_lead=keyword_lead,
            uncertain=True,
            mode="fallback",
        )
        return self._prepare_fallback(
            req,
            question=question,
            suggest_lead=suggest_lead,
            search_query=question,
            chunks=[],
            profile=profile,
            page_url=page_url,
        )

    def _system_prompt(self, prepared: _Prepared) -> str:
        if prepared.mode == "fallback":
            return FALLBACK_SYSTEM_PROMPT
        return SYSTEM_PROMPT_LITE if prepared.profile.use_lite_prompt else SYSTEM_PROMPT

    def _fallback_regenerate(self, prepared: _Prepared) -> str:
        relevance = classify_andes_relevance(
            self.gemini,
            prepared.question,
            history=prepared.history,
            conversation_summary=prepared.prior_summary,
        )
        if relevance != "related":
            return localized_out_of_scope(prepared.question)

        weak = self._weak_context(prepared)
        fb_prompt = build_fallback_user_prompt(
            prepared.question,
            history=prepared.history,
            conversation_summary=prepared.prior_summary,
            weak_context=weak,
        )
        reply = self.gemini.generate_answer(
            FALLBACK_SYSTEM_PROMPT,
            fb_prompt,
            max_output_tokens=220,
        )
        return filter_fallback_reply(reply, weak_context=weak)

    def _generate_reply(self, prepared: _Prepared) -> str:
        max_tokens = 220 if prepared.mode == "fallback" else prepared.profile.max_output_tokens
        reply = self.gemini.generate_answer(
            self._system_prompt(prepared),
            prepared.user_prompt,
            max_output_tokens=max_tokens,
        )
        weak = self._weak_context(prepared)
        if prepared.mode == "fallback":
            return filter_fallback_reply(reply, weak_context=weak)
        if self.settings.enable_gemini_fallback and _looks_uncertain(reply):
            return self._fallback_regenerate(prepared)
        return reply

    def _finalize_reply(self, prepared: _Prepared, reply: str) -> str:
        reply = reply.strip()
        if not reply:
            return localized_no_answer(prepared.question)
        weak = self._weak_context(prepared)
        if prepared.mode == "fallback":
            return filter_fallback_reply(reply, weak_context=weak)
        if self.settings.enable_gemini_fallback and _looks_uncertain(reply):
            return self._fallback_regenerate(prepared)
        return reply

    def _build_response(self, prepared: _Prepared, reply: str) -> ChatResponse:
        reply = strip_competitor_sentences(
            clamp_reply_brevity(clean_reply_citations(reply), prepared.question)
        )
        uncertain = prepared.mode == "fallback" or _looks_uncertain(reply)
        answer_mode = prepared.mode if prepared.mode == "fallback" else "rag"
        read_more = _pick_read_more(prepared.chunks, prepared.question, prepared.search_query)
        new_summary = update_conversation_summary(
            prior_summary=prepared.prior_summary,
            history=prepared.history,
            user_message=prepared.question,
            assistant_reply=reply,
        )

        return ChatResponse(
            reply=reply,
            sources=[
                {"url": c.url, "title": c.title, "score": round(c.similarity, 3)}
                for c in prepared.chunks[:3]
            ],
            read_more=read_more,
            suggest_lead_form=prepared.suggest_lead,
            show_lead_cta=False,
            uncertain=uncertain,
            answer_mode=answer_mode,
            conversation_summary=new_summary or None,
        )

    def handle(self, req: ChatRequest) -> ChatResponse:
        prepared = self._prepare(req)
        if isinstance(prepared, ChatResponse):
            return prepared
        reply = self._generate_reply(prepared)
        return self._build_response(prepared, reply)

    def stream(self, req: ChatRequest) -> Iterator[dict]:
        prepared = self._prepare(req)
        if isinstance(prepared, ChatResponse):
            yield {"type": "done", **prepared.model_dump(mode="json")}
            return

        max_tokens = 220 if prepared.mode == "fallback" else prepared.profile.max_output_tokens
        parts: list[str] = []
        for token in self.gemini.stream_answer(
            self._system_prompt(prepared),
            prepared.user_prompt,
            max_output_tokens=max_tokens,
        ):
            parts.append(token)
            yield {"type": "token", "text": token}

        reply = self._finalize_reply(prepared, "".join(parts))
        resp = self._build_response(prepared, reply)
        yield {"type": "done", **resp.model_dump(mode="json")}


def _pick_read_more(chunks, question: str, search_query: str | None = None) -> ReadMoreLink | None:
    if not chunks:
        return _fallback_read_more(question)
    q = (search_query or question).strip().lower()
    if len(q) < READ_MORE_MIN_QUESTION_CHARS and len(question.strip()) < READ_MORE_MIN_QUESTION_CHARS:
        return None
    if question.strip().lower() in SMALLTALK:
        return None
    top = chunks[0]
    if top.similarity < READ_MORE_MIN_SIMILARITY:
        return None
    title = (top.title or "our website").replace(" - Andes Technology", "").strip()
    label = f"Read more: {title}" if title else "Read more on our site"
    return ReadMoreLink(url=top.url, title=label)


def _fallback_read_more(question: str) -> ReadMoreLink | None:
    q = question.strip().lower()
    if len(q) < READ_MORE_MIN_QUESTION_CHARS or q in SMALLTALK:
        return None
    if any(k in q for k in ("product", "core", "cpu", "ip", "risc")):
        return ReadMoreLink(url=QUICK_LINKS[0]["url"], title="Browse products")
    if any(k in q for k in ("support", "tool", "sdk", "software")):
        return ReadMoreLink(url=QUICK_LINKS[2]["url"], title="Support & resources")
    if any(k in q for k in ("contact", "sales", "demo", "quote", "pricing", "license")):
        return ReadMoreLink(url=QUICK_LINKS[4]["url"], title="Contact us on the website")
    return ReadMoreLink(url=f"{SITE_BASE}/", title="Visit andestech.com")


def _suggests_lead_form(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in LEAD_INTENT_KEYWORDS)


def _should_suggest_lead(
    req: ChatRequest,
    question: str,
    *,
    keyword_lead: bool,
    uncertain: bool,
    mode: str,
) -> bool:
    if keyword_lead:
        return True
    if uncertain and mode == "fallback":
        return True
    if req.user_message_count >= 3 and any(
        k in question.lower() for k in ("product", "core", "license", "tool", "demo", "price", "quote")
    ):
        return True
    return False


def _looks_uncertain(reply: str) -> bool:
    lower = reply.lower()
    return any(p in lower for p in UNCERTAIN_PHRASES)
