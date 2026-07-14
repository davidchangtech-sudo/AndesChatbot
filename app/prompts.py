from __future__ import annotations

import re

from app.competitor_guard import COMPETITOR_PROMPT_RULE

SOURCE_CITATION_RE = re.compile(
    r"\s*\[(?:Source\s*)?\d+(?:\s*,\s*(?:Source\s*)?\d+)*\]",
    re.I,
)

BREVITY_RULE = (
    "LENGTH (strict): This is live chat, not a document. "
    "Default: 2–4 short sentences total. "
    "Simple questions → 1–2 sentences. "
    "Only use a short bullet list (max 4 bullets) if they explicitly asked to list/compare. "
    "Never write an essay, intro paragraph, or recap their question."
)

LANGUAGE_RULE = (
    "LANGUAGE: Always reply in the same language the visitor used in their latest message. "
    "If they write in Traditional Chinese, reply in Traditional Chinese; Japanese → Japanese; "
    "English → English; and so on. Keep Andes product names (AndesCore, AndeSight, RISC-V, etc.) "
    "in their original form. The site excerpts may be in English — translate the meaning into the "
    "visitor's language rather than quoting English verbatim."
)

SYSTEM_PROMPT = """You are the Andes AI Assistant on the Andes Technology website — a product specialist using only the excerpts provided each turn.

""" + BREVITY_RULE + """

""" + LANGUAGE_RULE + """

Identity:
- If asked who you are: Andes AI Assistant — RISC-V IP, tools, and how to reach our team.
- Professional applications engineer tone: calm, direct, helpful. No mascot energy.

Style:
- Match the visitor: short question → short answer.
- Plain English. "We" for Andes when natural.
- No filler openings ("Great question!", "Certainly!", etc.). No emoji unless they used emoji first.
- One honest "I don't have that in our materials" is enough — don't over-apologize.

Format:
- Chat bubbles, not articles. No citations or URLs in the body.
- No bullet walls unless they asked for a list.

Accuracy:
- Only facts from the excerpts. No invented specs, dates, customers, or pricing.
- Name specific Andes products/cores when the excerpts mention them.

""" + COMPETITOR_PROMPT_RULE + """

Website:
- They are already on andestech.com — don't tell them to visit the site.

Sales (only if they ask about pricing, licensing, demo, contact):
- Brief answer from excerpts, then one line: they can use **Book a meeting** in the chat."""

LEAD_INTENT_KEYWORDS = (
    "contact",
    "sales",
    "demo",
    "quote",
    "pricing",
    "partner",
    "license",
    "reach out",
    "get in touch",
    "speak to",
    "talk to",
    "email you",
    "call me",
    "representative",
    "buy",
    "purchase",
    "evaluation",
    "eval",
    "meeting",
    "consult",
    "support team",
    "human",
    "someone from andes",
)


SYSTEM_PROMPT_LITE = """You are the Andes AI Assistant on andestech.com. Answer only from the excerpts.

""" + BREVITY_RULE + """

""" + LANGUAGE_RULE + """

""" + COMPETITOR_PROMPT_RULE + """

- 1–3 sentences for most questions. Facts from excerpts only. No filler. No URLs."""


def clean_reply_citations(reply: str) -> str:
    """Remove inline [Source N] citations the model sometimes echoes."""
    if not reply:
        return reply
    lines = [SOURCE_CITATION_RE.sub("", line).rstrip() for line in reply.splitlines()]
    return "\n".join(lines).strip()


_DETAIL_HINTS = (
    "list",
    "compare",
    "difference",
    "differences",
    "which",
    "types of",
    "examples",
    "overview",
    "explain in detail",
    "tell me more",
)


def is_simple_definition_question(question: str) -> bool:
    q = question.strip().lower().rstrip("?.")
    return (
        q.startswith(("what is", "what are", "who is", "who are"))
        and len(q.split()) <= 7
    )


def question_wants_detail(question: str) -> bool:
    q = question.strip().lower()
    if len(q.split()) > 20:
        return True
    return any(h in q for h in _DETAIL_HINTS)


def clamp_reply_brevity(reply: str, question: str) -> str:
    """Hard cap when the model ignores length instructions."""
    text = (reply or "").strip()
    if not text:
        return text

    detailed = question_wants_detail(question)
    simple = is_simple_definition_question(question)
    max_sentences = 6 if detailed else (2 if simple else 3)
    max_chars = 800 if detailed else (260 if simple else 380)

    # Split on both Latin (. ! ?) and CJK (。！？) sentence endings.
    sentences = [s for s in re.split(r"(?<=[.!?。！？])\s*", text) if s.strip()]
    if len(sentences) > max_sentences:
        text = " ".join(sentences[:max_sentences]).strip()

    if len(text) > max_chars:
        cut = text[:max_chars]
        # Trim to last word boundary only when spaces exist (Latin scripts).
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        text = cut.rstrip(".,;:") + "…"
    return text


def build_context_block(
    chunks: list,
    max_chunk_chars: int = 1400,
) -> str:
    if not chunks:
        return "(No relevant website content was retrieved.)"

    parts = []
    for i, ch in enumerate(chunks, 1):
        title = ch.title or "Page"
        body = (ch.content or "")[:max_chunk_chars]
        if len(ch.content or "") > max_chunk_chars:
            body = body.rsplit(" ", 1)[0] + "…"
        block = f"Excerpt — {title}\n{body}"
        parts.append(block)
    return "\n\n---\n\n".join(parts)


def build_user_prompt(
    question: str,
    context: str,
    history: list | None = None,
    conversation_summary: str | None = None,
    *,
    lite: bool = False,
) -> str:
    if lite and not history and not (conversation_summary or "").strip():
        return f"""Excerpts:
{context}

Question: {question}

Reply in 1–2 sentences. One definition + one supporting detail max. Excerpts only."""

    convo_block = ""
    summary = (conversation_summary or "").strip()
    recent_lines: list[str] = []
    for msg in (history or [])[-4:]:
        role = "Visitor" if msg.role == "user" else "Assistant"
        recent_lines.append(f"{role}: {msg.content.strip()[:500]}")

    if summary:
        convo_block = (
            "Conversation summary (full thread — use this to resolve \"it\", \"that\", \"they\", "
            "and follow-ups):\n"
            f"{summary}\n\n---\n\n"
        )
        if recent_lines:
            convo_block += "Most recent turns:\n" + "\n".join(recent_lines) + "\n\n---\n\n"
    elif recent_lines:
        convo_block = "Recent conversation:\n" + "\n".join(recent_lines) + "\n\n---\n\n"

    repeat_note = ""
    q_norm = question.strip().lower()
    prior_user = [m.content.strip().lower() for m in (history or []) if m.role == "user"]
    if q_norm in prior_user:
        repeat_note = (
            "The visitor asked this same question before — answer with the same facts "
            "but clearly different wording than your earlier reply.\n\n"
        )

    return f"""{convo_block}{repeat_note}Site excerpts for this turn:

{context}

---

Visitor message: {question}

Reply in 2–4 sentences max unless they asked for a list. Excerpts only. No source numbers.
Answer the visitor message directly — do not recap the question."""

LEAD_NEEDS_SUMMARY_SYSTEM = """You write a brief sales handoff note for Andes Technology (RISC-V semiconductor IP).

Summarize what the visitor needs — do NOT paste the chat transcript or quote messages verbatim.

Output format (skip lines with no information):
• Looking for: ...
• Products / topics: ...
• Use case or application: ...
• Timeline / urgency: ...
• Other notes: ...

Rules:
- Under 100 words total
- Plain English, scannable bullets
- Focus on buyer intent and technical interest
- If there was no chat, summarize only from the meeting form fields"""
