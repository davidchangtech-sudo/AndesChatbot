#!/usr/bin/env python3
"""Verify retrieval picks the right pages (no Gemini calls)."""
from __future__ import annotations

import sys

from app.chat_service import ChatService, _Prepared
from app.config import get_settings
from app.models import ChatMessage, ChatRequest


def check(message: str, url_needle: str, history=None, summary=None) -> bool:
    svc = ChatService(get_settings())
    req = ChatRequest(message=message, history=history or [], conversation_summary=summary)
    prep = svc._prepare(req)
    if not isinstance(prep, _Prepared):
        print(f"FAIL {message!r}: early response")
        return False
    top = prep.chunks[0].url if prep.chunks else ""
    ok = url_needle.lower() in top.lower()
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {message!r}")
    print(f"       search: {prep.search_query[:80]}")
    print(f"       top:    {top}")
    return ok


def main() -> int:
    ok = True
    ok &= check("What is AndesCore?", "andescore-processors")
    ok &= check("What is AndeSight?", "andesight")
    history = [
        ChatMessage(role="user", content="What is AndesCore?"),
        ChatMessage(role="assistant", content="AndesCore is our RISC-V processor IP family."),
    ]
    summary = "Products/topics: AndesCore\nCurrent focus: AndesCore is our RISC-V processor IP family."
    ok &= check("tell me more about it", "andescore", history=history, summary=summary)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
