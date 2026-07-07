from __future__ import annotations
import re

from app.models import ChatMessage

MAX_SUMMARY_CHARS = 2000

_TOPIC_RE = re.compile(
    r"\b(?:Andes[A-Za-z™][\w-]*|N\d+[A-Za-z0-9-]*|D\d+[A-Za-z0-9-]*|"
    r"RISC-?V|AndeSight|AndesCore|AndesShape|AndesAIRE|AndesBoardFarm)\b",
    re.I,
)

_SMALLTALK = frozenset({"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye"})


def _extract_topics(text: str) -> list[str]:
    found = _TOPIC_RE.findall(text)
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _fast_summary(messages: list[ChatMessage], prior: str | None = None) -> str:
    parts: list[str] = []
    if prior and prior.strip():
        parts.append(prior.strip())

    user_topics: list[str] = []
    product_hits: list[str] = []
    assistant_gists: list[str] = []

    for msg in messages:
        text = (msg.content or "").strip()
        if not text:
            continue
        if msg.role == "user":
            if text.lower() not in _SMALLTALK:
                user_topics.append(text[:180])
            product_hits.extend(_extract_topics(text))
        else:
            first = re.split(r"\n+", text, maxsplit=1)[0][:200]
            assistant_gists.append(first)
            product_hits.extend(_extract_topics(text))

    if assistant_gists:
        focus = assistant_gists[-1][:240]
        prior_text = (prior or "").strip()
        if not prior_text or focus[:100] not in prior_text:
            parts.append("Current focus: " + focus)

    if product_hits:
        uniq: list[str] = []
        seen: set[str] = set()
        for p in product_hits:
            k = p.lower()
            if k not in seen:
                seen.add(k)
                uniq.append(p)
        parts.append("Products/topics: " + ", ".join(uniq[-8:]))

    if user_topics:
        parts.append("Visitor asked: " + " | ".join(user_topics[-4:]))

    if assistant_gists:
        parts.append("We discussed: " + " | ".join(assistant_gists[-2:]))

    out = "\n".join(parts).strip()
    return out[:MAX_SUMMARY_CHARS] if out else ""


def update_conversation_summary(
    *,
    prior_summary: str | None,
    history: list[ChatMessage],
    user_message: str,
    assistant_reply: str | None = None,
    **_kwargs,
) -> str:
    """Instant rolling summary — no API call (keeps chat fast)."""
    messages: list[ChatMessage] = list(history)
    user_message = user_message.strip()
    if user_message:
        messages.append(ChatMessage(role="user", content=user_message))
    if assistant_reply and assistant_reply.strip():
        messages.append(ChatMessage(role="assistant", content=assistant_reply.strip()))
    if not messages:
        return (prior_summary or "").strip()[:MAX_SUMMARY_CHARS]
    return _fast_summary(messages, prior_summary)


def _products_from_summary(summary: str) -> str:
    match = re.search(r"Products/topics:\s*(.+)", summary, re.I)
    if not match:
        return ""
    return match.group(1).split("\n")[0].strip()[:300]


def summary_for_search(summary: str | None, history: list[ChatMessage]) -> str:
    if summary and summary.strip():
        products = _products_from_summary(summary)
        if products:
            return products
        return summary.strip()[:600]
    return _fast_summary(history)[:600]
