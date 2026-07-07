from __future__ import annotations
"""Canonical Andes site URLs for the widget and chat fallbacks."""

SITE_BASE = "https://www.andestech.com/en"

QUICK_LINKS = [
    {"label": "Products", "url": f"{SITE_BASE}/products-solutions/"},
    {"label": "Solutions", "url": f"{SITE_BASE}/applications/"},
    {"label": "Support", "url": f"{SITE_BASE}/support/"},
    {"label": "About", "url": f"{SITE_BASE}/about/"},
    {"label": "Contact", "url": f"{SITE_BASE}/contact/"},
]

READ_MORE_MIN_SIMILARITY = 0.58
READ_MORE_MIN_QUESTION_CHARS = 14

SMALLTALK = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "bye",
        "goodbye",
        "yes",
        "no",
        "help",
    }
)
