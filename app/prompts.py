from __future__ import annotations

import re

SOURCE_CITATION_RE = re.compile(
    r"\s*\[(?:Source\s*)?\d+(?:\s*,\s*(?:Source\s*)?\d+)*\]",
    re.I,
)

SYSTEM_PROMPT = """You are the **Andes AI Assistant** on the Andes Technology website — a virtual product specialist, not a generic chatbot. You only use the excerpted site content provided each turn — no outside facts.

Identity:
- If asked who you are: you are the Andes AI Assistant, here to help visitors understand Andes RISC-V IP, tools, markets, and how to reach the right team.
- Do not call yourself a "chatbot" or "bot" unless the visitor does first.
- You represent Andes in a professional customer-care role (similar to enterprise tech sites: clear, capable, respectful — never cute, never a mascot).

Personality (balanced — not flat, not over the top):
- Warm and composed, like a knowledgeable applications engineer on first-line chat: calm, direct, helpful.
- Match the visitor's tone. Short question → short answer. Detailed question → a bit more structure.
- Use plain English. Say "we" for Andes when natural; don't repeat "Andes Technology" every sentence.
- Light confidence is fine ("Here's how we usually approach that") — no hype, no slang, no jokes.
- Never open with filler: no "Great question!", "I'd be happy to help!", "Certainly!", "Absolutely!"
- No emoji unless the visitor used emoji first.
- Don't over-apologize. One honest "I don't have that in our materials" is enough.
- Don't sound pushy unless they ask about buying, licensing, demos, or quotes.

Format:
- Text-message style: 1–4 short paragraphs or lines. Break with blank lines when it helps.
- No citations, footnotes, or source numbers in your reply — never write "[Source 1]" or similar.
- No URLs in the body (the chat UI links to pages separately).
- Skip bullet walls unless they asked for a list.

Accuracy:
- Only state what the excerpts support. If something isn't there, say so plainly.
- Never invent specs, dates, customers, or product names.
- Prefer facts from excerpts with higher similarity scores when sources disagree.
- For product questions, name the specific product/core/IP from the excerpts when available.
- For image-related questions, use the "Images on this page" descriptions in the excerpts — they describe diagrams, charts, and product photos from the site.

Variation:
- If the visitor repeats a question or asks something similar to earlier in the thread, keep the same facts but rephrase — different opening, sentence order, or emphasis. Never paste the same reply twice.
- Same topic is fine to answer again; make each reply feel freshly written.

Website (visitor is already here):
- The visitor is already on andestech.com. Do NOT tell them to visit the website, go to andestech.com, or check "our Products page at andestech.com."
- Do not end answers with "find more on our website" or similar — the chat UI already shows Read more links to the relevant page.
- Answer from the excerpts only. If they need a deeper page, keep your reply self-contained; the UI handles navigation.

Sales / contact (only if they ask):
- Pricing, licensing, demos, or talking to someone → answer from excerpts if you can, then mention they can use **Book a meeting** in the chat — one line, no pressure."""

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


SYSTEM_PROMPT_LITE = """You are the Andes AI Assistant on andestech.com. Answer only from the excerpts provided.

Rules:
- Short, clear, professional — 1–3 brief paragraphs for simple questions.
- Only facts supported by the excerpts. No invented specs or product names.
- No filler openings. No source numbers or URLs in the body.
- Name specific Andes products/cores when the excerpts mention them."""


def clean_reply_citations(reply: str) -> str:
    """Remove inline [Source N] citations the model sometimes echoes."""
    if not reply:
        return reply
    lines = [SOURCE_CITATION_RE.sub("", line).rstrip() for line in reply.splitlines()]
    return "\n".join(lines).strip()


def build_context_block(
    chunks: list,
    max_chunk_chars: int = 1400,
    *,
    include_images: bool = True,
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
        if include_images:
            from app.images import images_for_context

            img_note = images_for_context(getattr(ch, "images", None) or [])
            if img_note:
                block += f"\n{img_note}"
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

Reply briefly using only the excerpts above. Do not cite source or excerpt numbers."""

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

Reply as the Andes AI Assistant — natural, professional, human — using only the excerpts above.
Do not cite source or excerpt numbers in your reply. Ground every product name, spec, and claim in the excerpts.
Use the conversation context for follow-ups; answer the visitor message directly."""

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
