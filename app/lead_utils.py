from __future__ import annotations
import json
import logging

from app.config import Settings
from app.gemini_client import GeminiClient
from app.models import ChatMessage
from app.prompts import LEAD_NEEDS_SUMMARY_SYSTEM

logger = logging.getLogger(__name__)


def conversation_to_json(conversation: list[ChatMessage]) -> str:
    return json.dumps([m.model_dump() for m in conversation], ensure_ascii=False)


def _fallback_needs_summary(
    conversation: list[ChatMessage],
    *,
    topic: str | None,
    message: str,
    company: str | None,
) -> str:
    user_lines = [
        (m.content or "").strip()
        for m in conversation
        if m.role == "user" and (m.content or "").strip()
    ]
    parts: list[str] = []
    if topic:
        parts.append(f"• Interest: {topic}")
    if company:
        parts.append(f"• Company: {company}")
    if user_lines:
        snippet = " ".join(user_lines[-3:])
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."
        parts.append(f"• Visitor asked about: {snippet}")
    if message:
        first_line = message.strip().split("\n")[0]
        if first_line and first_line not in " ".join(user_lines):
            parts.append(f"• Meeting notes: {first_line}")
    if not parts:
        return "• No prior chat — see meeting form message above."
    return "\n".join(parts)


def _build_summary_prompt(
    conversation: list[ChatMessage],
    *,
    name: str,
    company: str | None,
    topic: str | None,
    message: str,
) -> str:
    chat_lines: list[str] = []
    for msg in conversation[-20:]:
        role = "Visitor" if msg.role == "user" else "Assistant"
        text = (msg.content or "").strip()
        if text:
            chat_lines.append(f"{role}: {text}")

    chat_block = "\n".join(chat_lines) if chat_lines else "(No chat before form)"

    return f"""Meeting form:
Name: {name}
Company: {company or "(not provided)"}
Interest: {topic or "(not provided)"}
Message: {message}

Chat before booking:
{chat_block}

Write the visitor needs summary for sales."""


def build_lead_needs_summary(
    conversation: list[ChatMessage],
    settings: Settings,
    *,
    name: str,
    company: str | None,
    topic: str | None,
    message: str,
) -> str:
    if not conversation and not (message or topic):
        return "• No chat history — see meeting form details above."

    try:
        client = GeminiClient(settings)
        user_prompt = _build_summary_prompt(
            conversation,
            name=name,
            company=company,
            topic=topic,
            message=message,
        )
        summary = client.summarize_text(LEAD_NEEDS_SUMMARY_SYSTEM, user_prompt)
        if summary:
            return summary.strip()
    except Exception:
        logger.exception("Lead needs summary failed — using fallback")

    return _fallback_needs_summary(
        conversation,
        topic=topic,
        message=message,
        company=company,
    )


# Kept for backwards compatibility if referenced elsewhere
def build_chat_summary(conversation: list[ChatMessage]) -> str:
    return _fallback_needs_summary(conversation, topic=None, message="", company=None)
