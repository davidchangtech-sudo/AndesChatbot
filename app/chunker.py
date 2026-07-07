from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class TextChunk:
    content: str
    word_count: int
    chunk_index: int


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def chunk_text(
    text: str,
    min_words: int = 500,
    max_words: int = 800,
) -> list[TextChunk]:
    """Split text into chunks of roughly 500–800 words, preferring paragraph boundaries."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_words = 0

    for para in paragraphs:
        para_words = _word_count(para)
        if para_words > max_words:
            flush()
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf: list[str] = []
            buf_words = 0
            for sent in sentences:
                sw = _word_count(sent)
                if buf_words + sw > max_words and buf:
                    chunks.append(" ".join(buf))
                    buf = [sent]
                    buf_words = sw
                else:
                    buf.append(sent)
                    buf_words += sw
            if buf:
                chunks.append(" ".join(buf))
            continue

        if current_words + para_words > max_words and current_words >= min_words:
            flush()

        current.append(para)
        current_words += para_words

        if current_words >= max_words:
            flush()

    flush()

    if not chunks and text:
        chunks = [text]

    return [
        TextChunk(content=c, word_count=_word_count(c), chunk_index=i)
        for i, c in enumerate(chunks)
    ]
