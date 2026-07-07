from __future__ import annotations
import time
from collections import OrderedDict
from typing import Iterator

import httpx
from google import genai
from google.genai import types

from app.config import Settings

GEMINI_MAX_ATTEMPTS = 4
GEMINI_CHAT_MAX_ATTEMPTS = 3
GEMINI_RETRY_DELAY_SECONDS = 2.0
GEMINI_CHAT_RETRY_DELAY_SECONDS = 1.0
MAX_IMAGE_BYTES = 4_000_000
_QUERY_EMBED_CACHE_MAX = 128

_query_embed_cache: OrderedDict[str, list[float]] = OrderedDict()

IMAGE_LABEL_PROMPT = """You label images from the Andes Technology (RISC-V semiconductor IP) website for search.

Page title: {title}
Page URL: {page_url}
HTML alt text: {alt}
Caption / nearby heading (if any): {context}

Write ONE sentence describing what the image shows (product name, diagram type, chip, board, etc.).

If the image is ONLY: a logo, icon, stock-market UI, financial table screenshot, generic navigation, unrelated third-party site, or not useful for product questions, respond exactly:
REJECT: <short reason>"""


def _cache_get(key: str) -> list[float] | None:
    hit = _query_embed_cache.get(key)
    if hit is not None:
        _query_embed_cache.move_to_end(key)
    return hit


def _cache_put(key: str, value: list[float]) -> None:
    _query_embed_cache[key] = value
    _query_embed_cache.move_to_end(key)
    while len(_query_embed_cache) > _QUERY_EMBED_CACHE_MAX:
        _query_embed_cache.popitem(last=False)


class GeminiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = genai.Client(api_key=settings.google_api_key)

    def _retry(self, fn, *, max_attempts: int = GEMINI_MAX_ATTEMPTS, delay: float = GEMINI_RETRY_DELAY_SECONDS):
        last_err: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return fn()
            except Exception as exc:
                last_err = exc
                if attempt + 1 < max_attempts:
                    time.sleep(delay * (attempt + 1))
        assert last_err is not None
        raise last_err

    def embed_document(self, text: str) -> list[float]:
        return self._embed(text, task_type="RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        key = text.strip().lower()[:400]
        cached = _cache_get(key)
        if cached is not None:
            return cached
        vector = self._embed(text, task_type="RETRIEVAL_QUERY")
        _cache_put(key, vector)
        return vector

    def _embed(self, text: str, task_type: str) -> list[float]:
        def call():
            result = self._client.models.embed_content(
                model=self.settings.gemini_embedding_model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.settings.embedding_dimensions,
                ),
            )
            if not result.embeddings:
                raise RuntimeError("Gemini returned no embeddings")
            values = result.embeddings[0].values
            if not values:
                raise RuntimeError("Empty embedding vector")
            return list(values)

        return self._retry(call)

    def generate_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int = 448,
    ) -> str:
        def call():
            response = self._client.models.generate_content(
                model=self.settings.gemini_chat_model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.45,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned empty response")
            return response.text.strip()

        return self._retry(
            call,
            max_attempts=GEMINI_CHAT_MAX_ATTEMPTS,
            delay=GEMINI_CHAT_RETRY_DELAY_SECONDS,
        )

    def classify_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int = 16,
    ) -> str:
        def call():
            response = self._client.models.generate_content(
                model=self.settings.gemini_chat_model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned empty classification")
            return response.text.strip()

        return self._retry(
            call,
            max_attempts=GEMINI_CHAT_MAX_ATTEMPTS,
            delay=GEMINI_CHAT_RETRY_DELAY_SECONDS,
        )

    def stream_answer(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int = 448,
    ) -> Iterator[str]:
        def produce() -> Iterator[str]:
            stream = self._client.models.generate_content_stream(
                model=self.settings.gemini_chat_model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.45,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text

        # Retry wrapper for stream start failures only
        last_err: Exception | None = None
        for attempt in range(GEMINI_CHAT_MAX_ATTEMPTS):
            try:
                yield from produce()
                return
            except Exception as exc:
                last_err = exc
                if attempt + 1 < GEMINI_CHAT_MAX_ATTEMPTS:
                    time.sleep(GEMINI_CHAT_RETRY_DELAY_SECONDS * (attempt + 1))
        assert last_err is not None
        raise last_err

    def summarize_text(self, system_prompt: str, user_prompt: str) -> str:
        def call():
            response = self._client.models.generate_content(
                model=self.settings.gemini_chat_model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.25,
                    max_output_tokens=384,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini returned empty summary")
            return response.text.strip()

        return self._retry(call)

    def label_image(self, image_url: str, page_title: str, page_url: str, alt: str = "", context: str = "") -> str:
        def call():
            resp = httpx.get(image_url, timeout=20.0, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            if len(data) > MAX_IMAGE_BYTES:
                return "REJECT: image too large"
            mime = (resp.headers.get("content-type") or "image/png").split(";")[0].strip()
            if not mime.startswith("image/"):
                mime = "image/png"
            prompt = IMAGE_LABEL_PROMPT.format(
                title=page_title or "Page",
                page_url=page_url,
                alt=alt or "(none)",
                context=context or "(none)",
            )
            response = self._client.models.generate_content(
                model=self.settings.gemini_chat_model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(text=prompt),
                            types.Part.from_bytes(data=data, mime_type=mime),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=120),
            )
            if not response.text:
                return "REJECT: empty label"
            return response.text.strip().split("\n")[0][:300]

        return self._retry(call)
