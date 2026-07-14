from __future__ import annotations

import re

from app.retrieval import NAMED_PRODUCT_SLUGS, TOPIC_HINT_RE, normalize_question

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "who",
        "how",
        "why",
        "when",
        "where",
        "tell",
        "me",
        "more",
        "about",
        "it",
        "that",
        "this",
        "and",
        "or",
        "for",
        "with",
        "from",
        "does",
        "do",
        "can",
        "you",
        "your",
        "our",
        "we",
        "be",
        "of",
        "in",
        "on",
        "to",
    }
)


def extract_search_tokens(query: str) -> list[str]:
    q = normalize_question(query.replace("™", ""))
    tokens: list[str] = []

    for match in TOPIC_HINT_RE.finditer(query):
        token = match.group(0).lower().replace("™", "")
        if token and token not in tokens:
            tokens.append(token)

    for slug in NAMED_PRODUCT_SLUGS:
        compact = slug.replace("-", "")
        if slug in q.replace("-", " ").replace("_", " ") or compact in q.replace("-", "").replace(" ", ""):
            if slug not in tokens:
                tokens.append(slug)

    for word in re.findall(r"[a-z0-9][a-z0-9-]{2,}", q):
        if word in _STOPWORDS or word in tokens:
            continue
        if word.isdigit():
            continue
        tokens.append(word)

    return tokens[:12]


def keyword_score_row(title: str, content: str, tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    title_l = (title or "").lower()
    content_l = (content or "").lower()
    score = 0.0
    for token in tokens:
        if token in title_l:
            score += 3.0
        if token in content_l:
            score += 1.0
        compact = token.replace("-", "")
        if compact and compact != token:
            if compact in title_l.replace("-", ""):
                score += 2.0
            if compact in content_l.replace("-", ""):
                score += 0.75
    return score


def merge_hybrid_chunks(vector_chunks: list, keyword_chunks: list, *, limit: int) -> list:
    """Merge vector + keyword hits, keeping the best score per chunk id."""
    best: dict[str, object] = {}

    def consider(chunk, sim: float) -> None:
        key = chunk.id or (chunk.url or "") + str(getattr(chunk, "chunk_index", 0))
        prev = best.get(key)
        if prev is None or sim > prev.similarity:
            chunk.similarity = sim
            best[key] = chunk

    for chunk in vector_chunks:
        consider(chunk, chunk.similarity)

    for chunk in keyword_chunks:
        # Keyword hits arrive with a lexical score mapped into similarity.
        consider(chunk, max(chunk.similarity, 0.48))

    out = list(best.values())
    out.sort(key=lambda c: c.similarity, reverse=True)
    return out[:limit]
