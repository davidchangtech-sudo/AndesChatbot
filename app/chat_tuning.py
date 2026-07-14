from __future__ import annotations

from dataclasses import dataclass

from app.retrieval import _needs_history_context
from app.site_links import SMALLTALK


@dataclass(frozen=True)
class PromptProfile:
    chunk_count: int
    max_chunk_chars: int
    max_output_tokens: int
    use_lite_prompt: bool


def is_greeting_or_smalltalk(message: str) -> bool:
    q = message.strip().lower().rstrip("!?.")
    return not q or q in SMALLTALK or q in {"thanks", "thank you", "bye", "goodbye", "ok", "okay"}


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
    if is_follow_up(message, history_len, has_summary):
        return PromptProfile(3, 750, max_output_tokens=200, use_lite_prompt=True)

    return PromptProfile(3, 550, max_output_tokens=110, use_lite_prompt=True)
