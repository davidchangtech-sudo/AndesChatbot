#!/usr/bin/env python3
"""Build s3-demo/ for static hosting (S3 website, CloudFront, etc.)."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_WIDGET = ROOT / "static" / "widget.js"
OUT = ROOT / "s3-demo"
SEED = ROOT / "data" / "seed_chunks.json"
ZIP_PATH = ROOT / "andes-chatbot-s3-demo.zip"

WIDGET_PATCH_START = """  var script = document.currentScript;
  var cfg = window.ANDES_CHAT_CONFIG || {};
  var demoMode = !!(cfg.demoMode || cfg.offline);
  var apiUrl =
    (cfg.apiUrl) ||
    (script && script.src ? new URL(script.src).origin : "");

  if (!apiUrl && !demoMode) {
    console.error("[Andes Chat] Missing apiUrl");
    return;
  }
"""

WIDGET_PATCH_ORIGINAL = """  var script = document.currentScript;
  var apiUrl =
    (window.ANDES_CHAT_CONFIG && window.ANDES_CHAT_CONFIG.apiUrl) ||
    (script && script.src ? new URL(script.src).origin : "");

  if (!apiUrl) {
    console.error("[Andes Chat] Missing apiUrl");
    return;
  }
"""

CHAT_FETCH_MARKER = '    fetch(apiUrl + "/chat", {'
CHAT_DEMO_BLOCK = """    if (demoMode && window.AndesDemoEngine) {
      window.AndesDemoEngine.chat(text)
        .then(function (data) {
          typing.remove();
          appendMsg(data.reply, "bot");
          if (data.read_more) appendReadMore(data.read_more);
          afterChatResponse(data);
        })
        .catch(function () {
          typing.remove();
          appendMsg(
            "I wasn't able to load the knowledge catalog — refresh the page and try again.",
            "bot"
          );
        });
      return;
    }
    fetch(apiUrl + "/chat", {"""

LEADS_FETCH_MARKER = '    fetch(apiUrl + "/leads", {'
LEADS_DEMO_BLOCK = """    if (demoMode && window.AndesDemoEngine) {
      window.AndesDemoEngine.submitLead(payload)
        .then(function (data) {
          showLeadSuccess();
          $("andes-lead-name").value = "";
          $("andes-lead-email").value = "";
          $("andes-lead-phone").value = "";
          clearEmailInvalid();
          $("andes-lead-company").value = "";
          $("andes-lead-interest").value = "";
          $("andes-lead-message").value = "";
          $("andes-lead-submit").disabled = false;
          $("andes-lead-submit").textContent = "Send request";
        })
        .catch(function (err) {
          $("andes-lead-submit").disabled = false;
          $("andes-lead-submit").textContent = "Send request";
          alert(err.message || "Could not save in demo mode.");
        });
      return;
    }
    fetch(apiUrl + "/leads", {"""


def build_widget() -> str:
    text = SRC_WIDGET.read_text(encoding="utf-8")
    if WIDGET_PATCH_ORIGINAL not in text:
        raise SystemExit("widget.js layout changed — update build_s3_demo.py patches")
    text = text.replace(WIDGET_PATCH_ORIGINAL, WIDGET_PATCH_START, 1)
    if CHAT_FETCH_MARKER not in text:
        raise SystemExit("chat fetch marker missing in widget.js")
    text = text.replace(CHAT_FETCH_MARKER, CHAT_DEMO_BLOCK, 1)
    if LEADS_FETCH_MARKER not in text:
        raise SystemExit("leads fetch marker missing in widget.js")
    text = text.replace(LEADS_FETCH_MARKER, LEADS_DEMO_BLOCK, 1)
    return text


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)

    shutil.copy2(SEED, OUT / "kb.json")
    (OUT / "widget.js").write_text(build_widget(), encoding="utf-8")
    assets_src = ROOT / "static" / "assets"
    index_src = ROOT / "static" / "test.html"
    if index_src.is_file():
        html = index_src.read_text(encoding="utf-8")
        html = html.replace("/static/assets/", "assets/")
        html = html.replace('src="/widget.js?v=50"', 'src="widget.js?v=50"')
        html = html.replace('src="/widget.js?v=49"', 'src="widget.js?v=50"')
        html = html.replace('src="/widget.js?v=41"', 'src="widget.js?v=50"')
        html = html.replace(
            "Demo mode: offline Andes knowledge catalog (full site index when crawl is allowed).",
            "Demo mode: offline Andes knowledge catalog.",
        )
        demo_cfg = """    window.ANDES_CHAT_CONFIG = {
      demoMode: true,
      kbUrl: "kb.json",
      logoUrl: "assets/andes-logo.png",
      logoWhiteUrl: "assets/andes-logo-white.png",
      launcherTooltip: "Chat with the Andes AI Assistant",
    };"""
        html = html.replace(
            """    window.ANDES_CHAT_CONFIG = {
      apiUrl: window.location.origin,
      launcherTooltip: "Chat with the Andes AI Assistant",
    };""",
            demo_cfg,
        )
        html = html.replace(
            "· Local demo page for chatbot widget testing",
            "· S3 static demo",
        )
        insert = '  <script src="demo-engine.js"></script>\n  '
        html = html.replace('  <script src="widget.js?v=50"></script>', insert + '<script src="widget.js?v=50"></script>')
        html = html.replace('  <script src="widget.js?v=49"></script>', insert + '<script src="widget.js?v=50"></script>')
        html = html.replace('  <script src="widget.js?v=41"></script>', insert + '<script src="widget.js?v=50"></script>')
        (OUT / "index.html").write_text(html, encoding="utf-8")
    assets_src = ROOT / "static" / "assets"
    if assets_src.is_dir():
        for png in assets_src.glob("*.png"):
            shutil.copy2(png, OUT / "assets" / png.name)

    upload = OUT / "UPLOAD.txt"
    upload.write_text(
        """Andes AI Assistant — S3 static demo
=====================================

Upload the entire s3-demo/ folder to your bucket (or use andes-chatbot-s3-demo.zip).

S3 website hosting
------------------
1. Create a bucket (e.g. andes-chatbot-demo).
2. Upload all files keeping paths (index.html at root).
3. Bucket → Properties → Static website hosting → Enable, index document: index.html
4. Bucket policy: allow public read on objects (or use CloudFront OAC).
5. Open the website endpoint URL.

CloudFront (recommended)
------------------------
Origin = S3 website endpoint or REST origin. Default root object: index.html

Refresh after code changes
--------------------------
  python scripts/build_s3_demo.py

Demo limits
-----------
- Answers use keyword + catalog search (not Gemini).
- Leads save to browser localStorage only (key: andes_demo_leads).
- Point widget at a live API by setting apiUrl and demoMode: false in index.html.

""",
        encoding="utf-8",
    )

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUT))

    chunks = json.loads((OUT / "kb.json").read_text(encoding="utf-8"))
    print(f"Built {OUT} ({len(chunks)} KB chunks)")
    print(f"Zip: {ZIP_PATH}")


if __name__ == "__main__":
    main()
