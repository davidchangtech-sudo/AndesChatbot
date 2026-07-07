from __future__ import annotations
"""Keyword fallbacks when vector search returns nothing (no crawl required)."""

from app.site_links import QUICK_LINKS, SITE_BASE

_GREETINGS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "help",
        "start",
    }
)

_THANKS = frozenset({"thanks", "thank you", "thx"})
_BYE = frozenset({"bye", "goodbye", "see you"})


def offline_greeting_reply() -> str:
    return (
        "Hello — I'm the Andes AI Assistant. I can help with AndesCore processors, "
        "AndeSight tools, markets (AI, automotive, IoT, 5G), and how licensing and support work.\n\n"
        "What would you like to explore?"
    )


def instant_reply(question: str) -> str | None:
    """Zero-API replies for greetings and pleasantries."""
    q = question.lower().strip().rstrip("!?.")
    if q in _GREETINGS:
        return offline_greeting_reply()
    if q in _THANKS:
        return "You're welcome. Ask anytime if you want details on our RISC-V cores, tools, or support."
    if q in _BYE:
        return "Goodbye — feel free to open the chat again if you have more questions about Andes products."
    return None


def offline_keyword_reply(question: str) -> str | None:
    q = question.lower().strip()
    if q in _GREETINGS or q.rstrip("!?.") in _GREETINGS:
        return offline_greeting_reply()

    if any(k in q for k in ("price", "pricing", "quote", "royalty", "cost", "license fee")):
        return (
            "Licensing and royalties depend on core choice, volume, and support package — "
            "Andes doesn't publish a single public price list.\n\n"
            "Use Contact sales below or the contact page on andestech.com for a quote."
        )

    if any(k in q for k in ("andesight", "ide", "toolchain", "compiler", "debug")):
        return (
            "AndeSight is Andes IDE for building and debugging software on AndesCore — "
            "cross-compile, debug on simulator or FPGA, and profile workloads.\n\n"
            "More on the Products & Solutions area of andestech.com."
        )

    if any(k in q for k in ("andescore", "core", "cpu", "processor", "risc-v", "riscv")):
        return (
            "AndesCore is our family of licensable RISC-V CPU IP — from compact IoT cores "
            "to higher-performance application processors, with optional vector and FuSa options.\n\n"
            "See AndesCore on andestech.com for current families and docs."
        )

    if any(k in q for k in ("fusa", "functional safety", "iso 26262", "automotive safety")):
        return (
            "Andes offers FuSa-oriented processor packages and safety documentation for "
            "automotive and industrial programs. Scope depends on the specific qualified core — "
            "talk to sales for ISO 26262 / IEC 61508 alignment."
        )

    if any(k in q for k in ("ace", "custom instruction", "custom extension")):
        return (
            "Andes Custom Extension (ACE) lets you add verified custom instructions with "
            "toolchain support — useful for crypto, DSP-like kernels, or domain-specific ops."
        )

    return None
