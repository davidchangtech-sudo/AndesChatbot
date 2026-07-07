#!/usr/bin/env python3
"""Smoke-test chat accuracy against the local knowledge base."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field

from app.chat_service import ChatService
from app.config import get_settings
from app.models import ChatMessage, ChatRequest


@dataclass
class Turn:
    message: str
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    source_url_contains: str | None = None


@dataclass
class Scenario:
    name: str
    turns: list[Turn]


SCENARIOS = [
    Scenario(
        name="AndesCore product question",
        turns=[
            Turn(
                "What is AndesCore?",
                must_contain=["andes", "processor"],
                source_url_contains="andescore",
            ),
            Turn(
                "tell me more about it",
                must_contain=["andes"],
                must_not_contain=["financial", "revenue", "stock"],
                source_url_contains="andescore",
            ),
        ],
    ),
    Scenario(
        name="AndeSight tools",
        turns=[
            Turn(
                "What is AndeSight?",
                must_contain=["andes"],
                source_url_contains="andesight",
            ),
        ],
    ),
    Scenario(
        name="Company identity",
        turns=[
            Turn(
                "Who is Andes Technology?",
                must_contain=["andes", "risc"],
            ),
        ],
    ),
    Scenario(
        name="Unsupported fact honesty",
        turns=[
            Turn(
                "What was Andes revenue in 1999?",
                must_contain=["don't", "not", "material", "have", "1999"],
            ),
        ],
    ),
]


def run_scenario(svc: ChatService, scenario: Scenario) -> tuple[int, int]:
    passed = 0
    failed = 0
    history: list[ChatMessage] = []
    summary: str | None = None

    print(f"\n=== {scenario.name} ===")
    for turn in scenario.turns:
        req = ChatRequest(message=turn.message, history=history, conversation_summary=summary)
        t0 = time.perf_counter()
        try:
            resp = svc.handle(req)
        except Exception as exc:
            print(f"  [ERROR] {turn.message!r}: {exc}")
            failed += 1
            continue
        elapsed = time.perf_counter() - t0
        reply = (resp.reply or "").lower()
        ok = True
        reasons: list[str] = []

        for needle in turn.must_contain:
            if needle.lower() not in reply:
                ok = False
                reasons.append(f"missing '{needle}'")

        for bad in turn.must_not_contain:
            if bad.lower() in reply:
                ok = False
                reasons.append(f"unwanted '{bad}'")

        if turn.source_url_contains:
            urls = " ".join(s.get("url", "") for s in resp.sources).lower()
            if turn.source_url_contains.lower() not in urls:
                ok = False
                reasons.append(f"source missing '{turn.source_url_contains}' (got {urls[:120]})")

        if resp.uncertain and turn.must_contain:
            # uncertain is fine only for honesty scenario
            pass

        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {turn.message!r} ({elapsed:.1f}s)")
        print(f"         reply: {resp.reply[:160].replace(chr(10), ' ')}...")
        if resp.sources:
            print(f"         source: {resp.sources[0].get('url', '')[:80]}")
        if not ok:
            print(f"         -> {', '.join(reasons)}")
            failed += 1
        else:
            passed += 1

        history.append(ChatMessage(role="user", content=turn.message))
        history.append(ChatMessage(role="assistant", content=resp.reply))
        summary = resp.conversation_summary

    return passed, failed


def main() -> int:
    settings = get_settings()
    svc = ChatService(settings)
    total_pass = 0
    total_fail = 0

    print(f"KB chunks: {getattr(svc.store, 'chunk_count', lambda: 0)()}")

    for scenario in SCENARIOS:
        p, f = run_scenario(svc, scenario)
        total_pass += p
        total_fail += f

    print(f"\nResult: {total_pass} passed, {total_fail} failed")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
