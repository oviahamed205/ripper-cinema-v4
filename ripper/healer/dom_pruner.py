"""
ripper.healer.dom_pruner
~~~~~~~~~~~~~~~~~~~~~~~~

High-speed semantic DOM compressor inspired by Crawl4AI.
Reduces multi-megabyte HTML documents into an ultra-dense (<4KB) structural
token outline optimized for local 1B-7B GGUF models.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set
from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger("ripper.healer.dom_pruner")

TAGS_TO_REMOVE = {
    "script",
    "style",
    "svg",
    "path",
    "noscript",
    "iframe",
    "meta",
    "link",
    "canvas",
    "picture",
    "source",
    "header",
    "footer",
    "nav",
    "aside",
}

MEDIA_KEYWORDS = re.compile(
    r"(?:download|episode|season|1080p|720p|480p|2160p|4k|hevc|x264|x265|bluray|web-dl|"
    r"fastdl|hubcloud|vcloud|gdrive|drive|pixeldrain|filepress|mega|dropgalaxy|server|"
    r"watch\s*online|direct\s*download|links|batch|zip|mkv|mp4)",
    re.I,
)

HONEYPOT_BLACKLIST = re.compile(
    r"(?:vglist\.cv|vegamovies-apk\.com|adsterra|betting|casino|rummy|download-app)",
    re.I,
)


class DOMPruner:
    """
    Compresses HTML documents into structured semantic representations
    for low-overhead model inference.
    """

    def __init__(self, max_bytes: int = 4096):
        self.max_bytes = max_bytes

    def prune(self, html: str, base_url: str = "") -> str:
        """
        Executes semantic reduction, stripping noise and preserving media download containers.
        Returns a compact structured representation.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "html.parser")

        # 1. Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 2. Decompose unneeded tags
        for tag in soup.find_all(TAGS_TO_REMOVE):
            tag.decompose()

        # 3. Strip inline style and event handler attributes
        for tag in soup.find_all(True):
            attrs_to_remove = [k for k in tag.attrs if k.startswith("on") or k in ("style", "width", "height", "border")]
            for a in attrs_to_remove:
                del tag[a]

        # 4. Extract high-priority media nodes
        condensed_lines: List[str] = []
        seen_hrefs: Set[str] = set()

        # Identify headers
        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = h.get_text(separator=" ").strip()
            if text and len(text) > 3:
                clean_text = " ".join(text.split())
                condensed_lines.append(f"[{h.name.upper()}] {clean_text}")

        # Scan download divs and anchor links
        for a in soup.find_all("a"):
            href = a.get("href", "").strip()
            text = a.get_text(separator=" ").strip()
            title = a.get("title", "").strip()
            label = text or title or "Link"

            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Skip blacklisted honeypots
            if HONEYPOT_BLACKLIST.search(href):
                continue

            if href in seen_hrefs:
                continue

            clean_label = " ".join(label.split())

            # Prioritize links matching media keywords or containing download parameters
            if MEDIA_KEYWORDS.search(clean_label) or MEDIA_KEYWORDS.search(href) or any(c in clean_label.lower() for c in ["1080", "720", "480", "4k", "fast", "hub"]):
                condensed_lines.append(f"LINK: {clean_label} -> {href}")
                seen_hrefs.add(href)

        # Also capture button and form actions
        for btn in soup.find_all(["button", "form"]):
            action = btn.get("action", "") or btn.get("data-href", "") or btn.get("data-url", "")
            btn_text = btn.get_text(separator=" ").strip()
            if action and MEDIA_KEYWORDS.search(btn_text):
                condensed_lines.append(f"ACTION: {btn_text} -> {action}")

        # Assemble and clamp output
        output = "\n".join(condensed_lines)
        if len(output.encode("utf-8")) > self.max_bytes:
            output = output.encode("utf-8")[:self.max_bytes].decode("utf-8", errors="ignore")

        logger.debug(f"[DOMPruner] Compressed {len(html)} bytes -> {len(output)} bytes ({len(seen_hrefs)} links preserved)")
        return output
