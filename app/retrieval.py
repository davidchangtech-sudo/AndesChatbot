from __future__ import annotations
import re
from typing import TYPE_CHECKING, Sequence

from app.images import image_search_text, normalize_image_record
from app.models import MediaItem
from app.site_links import READ_MORE_MIN_SIMILARITY, SMALLTALK

if TYPE_CHECKING:
    from app.models import ChatMessage

PRODUCT_URL_MARKERS = (
    "/products-solutions/",
    "/andescore",
    "/andeshape",
    "/andesaire",
    "/applications/",
    "/products/",
    "/product/",
)

FINANCE_URL_MARKERS = (
    "/financial",
    "/monthly-sales",
    "/investor",
    "/annual-report",
    "/revenue",
    "/shareholder",
    "/material-information",
    "/stock/",
)

PRODUCT_INTENT_WORDS = (
    "product",
    "products",
    "processor",
    "processors",
    "core",
    "cpu",
    "ip",
    "risc",
    "andescore",
    "andeshape",
    "andesaire",
    "portfolio",
    "lineup",
    "offer",
    "solution",
    "chip",
    "soc",
    "platform",
    "tool",
    "sdk",
    "ide",
)

FINANCE_INTENT_WORDS = (
    "financial",
    "finance",
    "revenue",
    "sales",
    "earnings",
    "investor",
    "stock",
    "share",
    "quarter",
    "annual report",
)

VISUAL_KEYWORDS = (
    "image",
    "photo",
    "picture",
    "diagram",
    "block diagram",
    "architecture diagram",
    "chart",
    "screenshot",
    "illustration",
    "look like",
    "show me",
    "see the",
    "visual",
    "what does",
    "how does it look",
)

MEDIA_MIN_SIMILARITY = 0.55
GENERIC_ALT = frozenset({"page image", "image", ""})

FOLLOW_UP_PHRASES = (
    "tell me more",
    "more about",
    "more on",
    "more detail",
    "more info",
    "more information",
    "what about",
    "how about",
    "about it",
    "about that",
    "about this",
    "explain that",
    "explain it",
    "explain more",
    "elaborate",
    "go on",
    "continue",
    "what else",
    "anything else",
    "can you expand",
    "learn more",
    "does it",
    "do they",
    "is it",
    "are they",
    "why is that",
    "how does it",
    "how do they",
    "what is it",
    "what are they",
    "who are they",
)

TOPIC_HINT_RE = re.compile(
    r"\b(?:Andes[A-Za-z™][\w-]*|N\d+[A-Za-z0-9-]*|D\d+[A-Za-z0-9-]*|"
    r"RISC-?V|AndeSight|AndesCore|AndesShape|AndesAIRE)\b",
    re.I,
)

# Canonical site sections for named product lines (boost in rerank).
NAMED_PRODUCT_SLUGS: dict[str, tuple[str, ...]] = {
    "andescore": ("/products-solutions/andescore-processors", "/andescore-processors", "/andescore"),
    "andeshape": ("/products-solutions/andeshape", "/andeshape"),
    "andesaire": ("/products-solutions/andesaire", "/andesaire"),
    "andesight": ("/products-solutions/andesight", "/andesight-ide", "/andesight"),
    "andesboardfarm": ("/products-solutions/andesboardfarm", "/andesboardfarm"),
}

_BLOG_YEAR_RE = re.compile(r"/20\d{2}/")

STANDALONE_QUESTION_STARTS = (
    "what is ",
    "what are ",
    "who is ",
    "who are ",
    "how do ",
    "how does ",
    "how to ",
    "where is ",
    "where can ",
    "when is ",
    "why is ",
    "why does ",
    "can you tell me what ",
    "can you explain what ",
)


def normalize_question(question: str) -> str:
    q = question.strip().lower()
    q = re.sub(r"\byou prod\b", "your product", q)
    q = re.sub(r"\bwhat prod\b", "what product", q)
    q = re.sub(r"\bprod\b(?!\w)", "product", q)
    return q


def _has_product_signal(text: str) -> bool:
    lower = text.lower()
    if any(w in lower for w in PRODUCT_INTENT_WORDS):
        return True
    if any(w in lower for w in ("andes", "andesight", "risc-v", "risc v")):
        return True
    return TOPIC_HINT_RE.search(text) is not None


def _needs_history_context(question: str) -> bool:
    q = question.strip().lower()
    if not q or q in SMALLTALK:
        return False
    if any(phrase in q for phrase in FOLLOW_UP_PHRASES):
        return True
    if any(q.startswith(prefix) for prefix in STANDALONE_QUESTION_STARTS) and _has_product_signal(q):
        return False
    pronoun_hit = any(
        token in q.split()
        for token in ("it", "that", "this", "they", "them", "those", "one", "these")
    )
    if pronoun_hit and not _has_product_signal(q):
        return True
    words = q.split()
    if len(words) <= 8 and not _has_product_signal(q):
        if not any(q.startswith(prefix) for prefix in STANDALONE_QUESTION_STARTS):
            return True
    return False


def _topic_hints_from_history(history: Sequence["ChatMessage"]) -> list[str]:
    hints: list[str] = []
    for msg in history[-6:]:
        if msg.role != "assistant":
            continue
        text = (msg.content or "").strip()
        if not text:
            continue
        for match in TOPIC_HINT_RE.finditer(text):
            hints.append(match.group(0))
    out: list[str] = []
    seen: set[str] = set()
    for hint in reversed(hints):
        key = hint.lower()
        if key in seen:
            continue
        seen.add(key)
        out.insert(0, hint)
    return out


def _named_products_in_text(text: str) -> list[str]:
    lower = normalize_question(text.replace("™", ""))
    hits: list[str] = []
    for slug in NAMED_PRODUCT_SLUGS:
        if slug in lower.replace("-", "").replace(" ", ""):
            hits.append(slug)
    for match in TOPIC_HINT_RE.finditer(text):
        token = match.group(0).lower().replace("™", "")
        if token in NAMED_PRODUCT_SLUGS and token not in hits:
            hits.append(token)
    return hits


def _expand_product_query(question: str) -> str:
    """Add product-line context so embeddings hit canonical product pages."""
    q = question.strip()
    lower = normalize_question(q.replace("™", ""))
    if "what is andescore" in lower or "what are andescore" in lower:
        return f"AndesCore processors RISC-V CPU IP product line {q}"
    if "what is andesight" in lower:
        return f"AndeSight IDE development tools RISC-V {q}"
    if "what is andeshape" in lower:
        return f"AndesShape SoC platform {q}"
    if "what is andesaire" in lower:
        return f"AndesAIRE AI accelerator RISC-V {q}"
    named = _named_products_in_text(q)
    if named and any(p in lower for p in ("tell me more", "more about", "about it", "about that")):
        return f"{', '.join(named)} RISC-V {q}"
    return q


def resolve_search_query(
    question: str,
    history: Sequence["ChatMessage"] | None = None,
    conversation_summary: str | None = None,
) -> str:
    """
    Build the text used for vector search (embedding).
    For vague follow-ups ("tell me more about it"), combine recent topic context.
    """
    q = question.strip()
    if conversation_summary and conversation_summary.strip() and _needs_history_context(q):
        from app.conversation_summary import summary_for_search

        topic = summary_for_search(conversation_summary, history or [])
        return normalize_question(_expand_product_query(f"{topic} {q}"))

    if not history or not _needs_history_context(q):
        return normalize_question(_expand_product_query(q))

    prior_users = [m.content.strip() for m in history if m.role == "user" and m.content.strip()]
    topic_hints = _topic_hints_from_history(history)

    parts: list[str] = []
    if prior_users:
        parts.extend(prior_users[-2:])
    parts.extend(h for h in topic_hints if h not in parts)
    parts.append(q)

    combined = " ".join(parts)
    return normalize_question(_expand_product_query(combined))


def query_intents(question: str) -> set[str]:
    q = normalize_question(question)
    intents: set[str] = set()
    if any(w in q for w in PRODUCT_INTENT_WORDS):
        intents.add("product")
    if any(w in q for w in FINANCE_INTENT_WORDS):
        intents.add("finance")
    if any(w in q for w in VISUAL_KEYWORDS):
        intents.add("visual")
    if any(w in q for w in ("who are you", "what are you", "introduce yourself", "your name")):
        intents.add("identity")
    return intents


def is_product_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(m in lower for m in PRODUCT_URL_MARKERS)


def is_finance_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(m in lower for m in FINANCE_URL_MARKERS)


def rerank_chunks(chunks: list, question: str) -> list:
    if not chunks:
        return chunks
    intents = query_intents(question)
    named_products = _named_products_in_text(question)
    adjusted: list[tuple[float, object]] = []

    for chunk in chunks:
        score = chunk.similarity
        url = chunk.url or ""
        url_lower = url.lower()
        title_lower = (chunk.title or "").lower()

        if "product" in intents and "finance" not in intents:
            if is_product_url(url):
                score += 0.12
            if is_finance_url(url):
                score -= 0.18
        elif "finance" in intents and "product" not in intents:
            if is_finance_url(url):
                score += 0.10
            if is_product_url(url):
                score -= 0.08

        if "identity" in intents:
            if any(p in url_lower for p in ("/about", "/contact", "/agent-contacts")):
                score += 0.08
            if is_finance_url(url):
                score -= 0.12

        for product in named_products:
            markers = NAMED_PRODUCT_SLUGS.get(product, ())
            if any(marker in url_lower for marker in markers):
                score += 0.22
            if product in title_lower.replace("™", "").replace(" ", ""):
                score += 0.10
            if _BLOG_YEAR_RE.search(url_lower) and "/products-solutions/" not in url_lower:
                score -= 0.14

        adjusted.append((score, chunk))

    adjusted.sort(key=lambda pair: pair[0], reverse=True)
    reranked = []
    for score, chunk in adjusted:
        chunk.similarity = score
        reranked.append(chunk)
    return reranked


def dedupe_chunks_by_url(chunks: list) -> list:
    """Keep the best-scoring chunk per URL so the prompt isn't padded with duplicates."""
    best: dict[str, object] = {}
    for chunk in chunks:
        url = (chunk.url or "").strip()
        key = url or chunk.id
        prev = best.get(key)
        if prev is None or chunk.similarity > prev.similarity:
            best[key] = chunk
    out = list(best.values())
    out.sort(key=lambda c: c.similarity, reverse=True)
    return out


def _image_label(img: dict) -> str:
    return image_search_text(img) or (img.get("label") or img.get("alt") or "").strip()


def _image_usable(img: dict) -> bool:
    rec = normalize_image_record(img)
    label = image_search_text(rec)
    if not label or label.lower() in GENERIC_ALT:
        return False
    if label.upper().startswith("REJECT"):
        return False
    return bool(rec.get("url"))


def _label_matches_question(label: str, question: str) -> bool:
    q = normalize_question(question)
    words = {w for w in re.split(r"\W+", q) if len(w) > 2}
    label_lower = label.lower()
    hits = sum(1 for w in words if w in label_lower)
    if hits >= 1:
        return True
    for match in TOPIC_HINT_RE.finditer(question):
        token = match.group(0).lower()
        if token in label_lower:
            return True
    product_words = [w for w in PRODUCT_INTENT_WORDS if w in q]
    return any(w in label_lower for w in product_words)


def _score_image_for_query(img: dict, query_text: str) -> int:
    label = image_search_text(img).lower()
    if not label:
        return 0
    q = normalize_question(query_text)
    words = [w for w in re.split(r"\W+", q) if len(w) > 2]
    score = sum(2 for w in words if w in label)
    for match in TOPIC_HINT_RE.finditer(query_text):
        token = match.group(0).lower()
        if token in label:
            score += 4
    if any(k in q for k in ("diagram", "architecture", "block")) and any(
        k in label for k in ("diagram", "architecture", "block")
    ):
        score += 3
    if any(k in q for k in ("chart", "table", "graph")) and any(
        k in label for k in ("chart", "table", "graph")
    ):
        score += 3
    return score


def pick_media(chunks: list, question: str, search_query: str | None = None) -> MediaItem | None:
    if not chunks:
        return None
    q = question.strip().lower()
    if len(q) < 6 or q in SMALLTALK:
        return None

    query_text = f"{search_query or ''} {question}".strip()
    intents = query_intents(question)
    visual = "visual" in intents
    wants_diagram = any(
        k in normalize_question(question)
        for k in ("diagram", "architecture", "look like", "show me", "picture", "photo", "chart")
    )

    if not visual and not wants_diagram:
        return None

    min_score = 2

    best: MediaItem | None = None
    best_score = 0

    for chunk in chunks[:5]:
        if chunk.similarity < MEDIA_MIN_SIMILARITY:
            continue
        if is_finance_url(chunk.url or ""):
            continue

        for img in chunk.images or []:
            if not _image_usable(img):
                continue
            rec = normalize_image_record(img)
            label = image_search_text(rec)
            score = _score_image_for_query(rec, query_text)
            if score <= 0 and not visual:
                if not _label_matches_question(label, question):
                    continue
                score = 1
            if visual and chunk.similarity >= READ_MORE_MIN_SIMILARITY and score >= 1:
                score += 2
            if score > best_score:
                best_score = score
                caption = rec.get("description") or rec.get("label") or rec.get("alt") or "From andestech.com"
                best = MediaItem(url=rec["url"], alt=_clean_media_caption(caption))

    if best and best_score >= min_score:
        return best
    return None


def _clean_media_caption(text: str) -> str:
    text = re.sub(r"^This (image|diagram|chart|table|photo) (shows|is|illustrates)\s+", "", text, flags=re.I)
    return text.strip()[:200]
