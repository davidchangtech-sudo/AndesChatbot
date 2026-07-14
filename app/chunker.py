from __future__ import annotations

import re
from dataclasses import dataclass

# Latin and CJK sentence endings — never split mid-sentence.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass
class TextChunk:
    content: str
    word_count: int
    chunk_index: int


def _word_count(text: str) -> int:
    """Latin words + CJK characters (Chinese/Japanese text has few spaces)."""
    latin = len(re.findall(r"\b\w+\b", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", text))
    return latin + cjk


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return parts or [text]


def _paragraphs(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras or [text]


def _sentences_from_paragraphs(paragraphs: list[str]) -> list[str]:
    """Flatten paragraphs into sentences while keeping paragraph order."""
    out: list[str] = []
    for para in paragraphs:
        out.extend(_split_sentences(para))
    return out


def chunk_text(
    text: str,
    min_words: int = 500,
    max_words: int = 800,
    *,
    overlap_sentences: int = 2,
) -> list[TextChunk]:
    """Split text into chunks of roughly min_words–max_words.

    - Never cuts mid-sentence (Latin .!? or CJK 。！？).
    - Packs whole sentences up to max_words.
    - Repeats the last `overlap_sentences` sentences at the start of the next chunk
      so retrieval does not lose context at boundaries.
    """
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return []

    sentences = _sentences_from_paragraphs(paragraphs)
    if not sentences:
        return []

    raw_chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    new_since_flush = 0

    def flush(*, is_final: bool = False) -> None:
        nonlocal current, current_words, new_since_flush
        if not current:
            return
        # Trailing buffer is only overlap carry — already in the previous chunk.
        if (
            is_final
            and overlap_sentences > 0
            and raw_chunks
            and new_since_flush == 0
            and len(current) <= overlap_sentences
        ):
            current = []
            current_words = 0
            new_since_flush = 0
            return

        raw_chunks.append(" ".join(current))
        if overlap_sentences > 0 and len(current) > overlap_sentences:
            tail = current[-overlap_sentences:]
            current = tail[:]
            current_words = sum(_word_count(s) for s in current)
            new_since_flush = 0
        else:
            current = []
            current_words = 0
            new_since_flush = 0

    for sent in sentences:
        sw = _word_count(sent)

        # Rare: one sentence longer than max — keep whole (do not cut mid-sentence).
        if sw > max_words:
            flush()
            raw_chunks.append(sent)
            current = []
            current_words = 0
            new_since_flush = 0
            continue

        if current_words + sw > max_words and current_words >= min_words:
            flush()

        current.append(sent)
        current_words += sw
        new_since_flush += 1

        if current_words >= max_words:
            flush()

    flush(is_final=True)

    if not raw_chunks and text.strip():
        raw_chunks = [text.strip()]

    return [
        TextChunk(content=c, word_count=_word_count(c), chunk_index=i)
        for i, c in enumerate(raw_chunks)
    ]
