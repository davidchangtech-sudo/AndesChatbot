from __future__ import annotations
import re
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup

REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "nav",
    "footer",
    "header",
    ".nav",
    ".navbar",
    ".navigation",
    ".menu",
    ".footer",
    ".site-footer",
    "#footer",
    "#header",
    "#nav",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie-notice",
    ".wp-block-navigation",
    "aside",
    "form",
    ".social",
    ".share",
    ".related-posts",
    ".comments",
    "#comments",
]


def extract_page(html: str, url: str) -> tuple[str, str]:
    """
    Return (title, clean_body_text).
    Uses trafilatura with BeautifulSoup pre-cleaning for nav/footer noise.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(REMOVE_SELECTORS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()

    cleaned_html = str(soup.body or soup)
    downloaded = trafilatura.extract(
        cleaned_html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    text = (downloaded or soup.get_text(separator="\n")).strip()
    text = _normalize_text(text)
    return title, text


def _normalize_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def is_english_path(url: str, base_host: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc.replace("www.", "") != base_host.replace("www.", ""):
        return False
    path = parsed.path or "/"
    return path == "/" or path == "/en" or path.startswith("/en/")
