from __future__ import annotations

import re

# RISC-V / embedded CPU IP vendors and common comparison targets (not Andes partners-only mentions).
COMPETITOR_NAMES: tuple[str, ...] = (
    "sifive",
    "codasip",
    "synopsys",
    "imagination technologies",
    "imagination tech",
    "mips",
    "tenstorrent",
    "starfive",
    "nuclei system",
    "nuclei technology",
    "efinix",
    "semidynamics",
    "think silicon",
    "verisilicon",
    "c*core",
    "ccore",
    "wingsemi",
    "eswin",
    "xuante",
    "t-head",
    "thead",
    "alibaba cloud chip",
    "ventana micro",
    "ventana",
    "western digital risc",
)

# Build word-boundary patterns for single-token names.
_COMPETITOR_TOKEN_RE = re.compile(
    r"\b("
    r"sifive|codasip|synopsys|mips|tenstorrent|starfive|nuclei|efinix|"
    r"semidynamics|verisilicon|eswin|xuante|thead|t-head|ventana|"
    r"arm|aarch64|qualcomm|nvidia|xilinx|raspberry\s*pi"
    r")\b",
    re.I,
)

_COMPARE_RE = re.compile(
    r"\b("
    r"vs\.?|versus|compare|comparison|compared to|better than|worse than|"
    r"difference between|differences between|which is better|who is better|"
    r"alternative to|alternatives to|competitor|competitors|competing with|"
    r"compete with|rival|rivals"
    r")\b",
    re.I,
)

_COMPETITOR_URL_MARKERS: tuple[str, ...] = (
    "sifive",
    "codasip",
    "synopsys.com/arc",
    "starfive",
    "nuclei",
    "tenstorrent",
    "ventana",
    "t-head",
    "thead",
)

COMPETITOR_DECLINE_REPLY = (
    "I focus on Andes Technology — our RISC-V processor IP, tools, and licensing.\n\n"
    "I can't compare us to other vendors or speak for their products. "
    "Ask me about AndesCore, AndeSight, or our solutions, or use **Book a meeting** "
    "to speak with our team."
)

_COMPETITOR_DECLINE_LOCALIZED = {
    "zh": (
        "我主要說明晶心科技（Andes Technology）的 RISC-V 處理器 IP、工具與授權方式。\n\n"
        "我無法與其他廠商比較，也不能代表他們的產品發言。"
        "歡迎詢問 AndesCore、AndeSight 或我們的解決方案，"
        "或使用 **Book a meeting** 與我們的團隊聯繫。"
    ),
    "ja": (
        "私は Andes Technology の RISC-V プロセッサ IP、ツール、ライセンスについてお答えします。\n\n"
        "他社製品との比較や、他社に関する説明はできません。"
        "AndesCore、AndeSight、ソリューションについてお尋ねいただくか、"
        "**Book a meeting** から担当チームにご連繡ください。"
    ),
}


def _language_hint(text: str) -> str:
    for ch in text or "":
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF:
            return "ja"
        if 0x4E00 <= code <= 0x9FFF:
            return "zh"
    return "en"


def localized_competitor_decline(text: str) -> str:
    return _COMPETITOR_DECLINE_LOCALIZED.get(_language_hint(text), COMPETITOR_DECLINE_REPLY)


def mentions_competitor(text: str) -> bool:
    q = (text or "").lower()
    if _COMPETITOR_TOKEN_RE.search(q):
        return True
    return any(name.strip() in q for name in COMPETITOR_NAMES if len(name.strip()) > 4)


def is_competitor_question(question: str) -> bool:
    """True when the visitor is asking about or comparing other vendors."""
    q = (question or "").strip()
    if not q:
        return False
    lower = q.lower()

    if mentions_competitor(q):
        return True

    if _COMPARE_RE.search(lower):
        # Generic comparison without naming Andes — still block vendor shootouts.
        if any(
            k in lower
            for k in (
                "risc-v ip",
                "riscv ip",
                "cpu ip",
                "processor ip",
                "core ip",
                "embedded ip",
                "who should i choose",
                "which vendor",
                "which company",
            )
        ):
            return True

    return False


def is_competitor_focused_chunk(*, url: str = "", title: str = "", content: str = "") -> bool:
    """Drop KB excerpts that are mainly about other vendors."""
    blob = f"{url} {title} {content}".lower()
    url_l = (url or "").lower()
    if any(marker in url_l for marker in _COMPETITOR_URL_MARKERS):
        return True
    if mentions_competitor(blob):
        # Partnership headlines often name one competitor once — still competitor-centric.
        title_l = (title or "").lower()
        if mentions_competitor(title_l):
            return True
        # Body with multiple competitor tokens is not about Andes-only facts.
        hits = len(_COMPETITOR_TOKEN_RE.findall(blob))
        if hits >= 2:
            return True
        if hits == 1 and not any(
            k in blob for k in ("andestech", "andes technology", "andes core", "andescore", "andesight")
        ):
            return True
    return False


def filter_competitor_chunks(chunks: list) -> list:
    out = []
    for ch in chunks:
        if is_competitor_focused_chunk(
            url=getattr(ch, "url", "") or "",
            title=getattr(ch, "title", "") or "",
            content=getattr(ch, "content", "") or "",
        ):
            continue
        out.append(ch)
    return out


def strip_competitor_sentences(reply: str) -> str:
    """Remove sentences that center on competitor vendors from model output."""
    text = (reply or "").strip()
    if not text or not mentions_competitor(text):
        return text

    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    kept = [p for p in parts if p.strip() and not mentions_competitor(p)]
    if kept:
        return " ".join(kept).strip()
    return COMPETITOR_DECLINE_REPLY


COMPETITOR_PROMPT_RULE = (
    "Competitors: Never discuss, compare, recommend, or summarize other vendors' products "
    "(e.g. SiFive, Codasip, Synopsys, Arm, StarFive, Nuclei, Imagination, MIPS). "
    "If excerpts mention another company, ignore that material and answer only about Andes. "
    "If asked to compare or choose vendors, decline briefly and offer Andes facts or Book a meeting."
)
