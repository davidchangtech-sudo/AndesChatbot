from __future__ import annotations
"""Extract meaningful images from Andes website HTML pages."""

from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

SKIP_SRC_PARTS = (
    "logo",
    "icon",
    "favicon",
    "sprite",
    "emoji",
    "avatar",
    "placeholder",
    "spacer",
    "pixel",
    "1x1",
    "blank",
    "loading",
    "spinner",
    "gravatar",
    "wp-includes",
    "data:image/svg",
)
SKIP_EXTENSIONS = (".svg", ".gif")
GENERIC_ALT = frozenset({"page image", "image", "", "photo", "picture"})


def _clean_text(value: str | None, limit: int = 200) -> str:
    return (value or "").strip()[:limit]


def _is_generic(text: str) -> bool:
    return not text or text.lower() in GENERIC_ALT


def _build_description(*parts: str | None) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        text = _clean_text(part)
        if not text or _is_generic(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return " — ".join(out)


def _figcaption_for(img) -> str:
    parent = img.find_parent("figure")
    if not parent:
        return ""
    cap = parent.find("figcaption")
    return cap.get_text(" ", strip=True) if cap else ""


def _nearby_heading(img) -> str:
    for tag in img.find_all_previous(["h1", "h2", "h3", "h4"], limit=1):
        return _clean_text(tag.get_text(" ", strip=True), 120)
    return ""


def normalize_image_record(img: dict) -> dict:
    """Ensure consistent metadata fields on stored image dicts."""
    alt = _clean_text(img.get("alt"))
    title = _clean_text(img.get("title"))
    caption = _clean_text(img.get("caption"))
    aria = _clean_text(img.get("aria_label") or img.get("aria-label"))
    heading = _clean_text(img.get("heading"))
    label = _clean_text(img.get("label"))
    description = _clean_text(img.get("description")) or _build_description(
        label, caption, alt, title, aria, heading
    )
    return {
        "url": (img.get("url") or "").strip(),
        "alt": alt,
        "title": title,
        "caption": caption,
        "aria_label": aria,
        "heading": heading,
        "label": label,
        "description": description,
        "source": _clean_text(img.get("source"), 40),
    }


def image_search_text(img: dict) -> str:
    """Combined text used to match images to visitor questions."""
    rec = normalize_image_record(img)
    return " ".join(
        p
        for p in (
            rec.get("label"),
            rec.get("description"),
            rec.get("caption"),
            rec.get("alt"),
            rec.get("title"),
            rec.get("aria_label"),
            rec.get("heading"),
        )
        if p
    ).strip()


def image_context_line(img: dict) -> str:
    rec = normalize_image_record(img)
    text = image_search_text(rec)
    if not text or text.upper().startswith("REJECT"):
        return ""
    kind = ""
    lower = text.lower()
    if any(k in lower for k in ("block diagram", "architecture", "diagram", "block-diagram")):
        kind = "[diagram] "
    elif any(k in lower for k in ("chart", "graph", "table")):
        kind = "[chart] "
    elif "photo" in lower or "board" in lower:
        kind = "[photo] "
    return f"- {kind}{text[:220]}"


def extract_images(html: str, page_url: str, max_images: int = 6) -> list[dict]:
    """Return image records with url, alt, caption, and other page metadata."""
    soup = BeautifulSoup(html, "lxml")
    base = str(page_url)
    parsed_base = urlparse(base)
    host = parsed_base.netloc.replace("www.", "")

    found: list[dict] = []
    seen: set[str] = set()

    def add(
        raw_src: str | None,
        *,
        alt: str | None = None,
        title: str | None = None,
        caption: str | None = None,
        aria_label: str | None = None,
        heading: str | None = None,
        source: str = "img",
        priority: int = 0,
    ) -> None:
        if not raw_src or len(found) >= max_images:
            return
        src = urldefrag(urljoin(base, raw_src.strip()))[0]
        if not src or src in seen:
            return
        p = urlparse(src)
        if p.netloc.replace("www.", "") != host:
            return
        lower = src.lower()
        if any(part in lower for part in SKIP_SRC_PARTS):
            return
        if any(lower.endswith(ext) for ext in SKIP_EXTENSIONS):
            return
        seen.add(src)
        record = normalize_image_record(
            {
                "url": src,
                "alt": alt,
                "title": title,
                "caption": caption,
                "aria_label": aria_label,
                "heading": heading,
                "source": source,
            }
        )
        record["_priority"] = priority
        found.append(record)

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        og_alt = ""
        for prop in ("og:image:alt", "twitter:image:alt"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                og_alt = meta["content"]
                break
        add(
            og["content"],
            alt=og_alt,
            source="og:image",
            priority=10,
        )

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            srcset = img.get("srcset") or ""
            first = srcset.split(",")[0].strip().split()[0] if srcset else None
            src = first
        add(
            src,
            alt=img.get("alt"),
            title=img.get("title"),
            aria_label=img.get("aria-label"),
            caption=_figcaption_for(img),
            heading=_nearby_heading(img),
            source="img",
        )

    for tag in soup.find_all("source"):
        srcset = tag.get("srcset") or ""
        if srcset and "image" in (tag.get("type") or ""):
            first = srcset.split(",")[0].strip().split()[0]
            add(first, source="source")

    found.sort(key=lambda x: -x.pop("_priority", 0))
    return [normalize_image_record(i) for i in found[:max_images]]


def images_for_context(images: list[dict]) -> str:
    if not images:
        return ""
    lines = []
    for img in images[:4]:
        line = image_context_line(img)
        if line:
            lines.append(line)
    if not lines:
        return ""
    return "Images on this page (use descriptions for accuracy; do not invent visuals):\n" + "\n".join(lines)
