from __future__ import annotations

from dataclasses import dataclass

from app.retrieval import _needs_history_context, query_intents
from app.site_links import SMALLTALK

_VISUAL_HINTS = (
    "diagram",
    "image",
    "photo",
    "picture",
    "look like",
    "show me",
    "chart",
    "architecture",
)


@dataclass(frozen=True)
class PromptProfile:
    chunk_count: int
    max_chunk_chars: int
    include_images: bool
    max_output_tokens: int
    use_lite_prompt: bool


def is_greeting_or_smalltalk(message: str) -> bool:
    q = message.strip().lower().rstrip("!?.")
    return not q or q in SMALLTALK or q in {"thanks", "thank you", "bye", "goodbye", "ok", "okay"}


def wants_visual_context(message: str) -> bool:
    lower = message.strip().lower()
    if "visual" in query_intents(message):
        return True
    return any(h in lower for h in _VISUAL_HINTS)


def is_follow_up(message: str, history_len: int, has_summary: bool) -> bool:
    if history_len > 0 or has_summary:
        return True
    return _needs_history_context(message)


def prompt_profile(
    message: str,
    *,
    history_len: int = 0,
    has_summary: bool = False,
) -> PromptProfile:
    if wants_visual_context(message):
        return PromptProfile(4, 1100, include_images=True, max_output_tokens=512, use_lite_prompt=False)

    if is_follow_up(message, history_len, has_summary):
        return PromptProfile(4, 950, include_images=False, max_output_tokens=448, use_lite_prompt=False)

    # Simple standalone product / company questions — smallest fast path.
    return PromptProfile(3, 650, include_images=False, max_output_tokens=280, use_lite_prompt=True)
