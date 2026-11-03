"""
ripper.universal_engine.heuristics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ultra-fast, zero-browser semantic DOM extractor.
Uses token scoring and DOM tree clustering inspired by Scrapling and yt-dlp
to extract media download tiers, qualities, file sizes, audio tracks, and mirrors
from any unknown movie website layout without requiring site-specific CSS selectors.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup, Tag
import httpx

from ..models import ServerMirror
from ..media import (
    MediaDownloadItem,
    parse_movie_title_header,
    detect_language,
    DEFAULT_HEADERS,
)

# Regex Patterns for Universal Media Scoring
QUALITY_PATTERNS = [
    (re.compile(r"\b(?:4k|2160p|uhd)\b", re.I), "2160P"),
    (re.compile(r"\b(?:1080p|fhd)\b", re.I), "1080P"),
    (re.compile(r"\b(?:720p|hd)\b", re.I), "720P"),
    (re.compile(r"\b(?:480p|sd|360p)\b", re.I), "480P"),
]

CODEC_PATTERNS = [
    (re.compile(r"\b(?:x265|hevc|h\.?265)\b", re.I), "HEVC"),
    (re.compile(r"\b(?:x264|avc|h\.?264)\b", re.I), "X264"),
    (re.compile(r"\b(?:10bit|10-bit)\b", re.I), "10Bit"),
    (re.compile(r"\b(?:remux)\b", re.I), "REMUX"),
    (re.compile(r"\b(?:web-?dl|webrip)\b", re.I), "WEB-DL"),
    (re.compile(r"\b(?:bluray|bdrip)\b", re.I), "BluRay"),
    (re.compile(r"\b(?:hdr10\+?|hdr|dv|dolby vision)\b", re.I), "HDR"),
]

SIZE_REGEX = re.compile(
    r"\b(?:\[|\()?\s*(\d+(?:\.\d+)?)\s*(GB|MB|GiB|MiB|gb|mb)\s*(?:\]|\))?",
    re.I,
)

AUDIO_PATTERNS = [
    (re.compile(r"\b(?:dual\s*audio)\b", re.I), "Dual Audio"),
    (re.compile(r"\b(?:multi\s*audio)\b", re.I), "Multi Audio"),
    (re.compile(r"\b(?:hindi\s*dubbed|hindi\s*org|hindi)\b", re.I), "Hindi"),
    (re.compile(r"\b(?:english|eng)\b", re.I), "English"),
    (re.compile(r"\b(?:ddp?5\.1|dd5\.1|5\.1ch|atmos)\b", re.I), "5.1 Audio"),
]

SEASON_EP_REGEX = re.compile(
    r"\b(?:s(?:eason)?\s*(\d+))?(?:\s*e(?:pisode)?\s*(\d+))?\b",
    re.I,
)

# Ad networks & navigation noise exclusion list
DISCARD_DOMAINS = [
    "facebook.com", "twitter.com", "t.me", "telegram.me", "instagram.com",
    "whatsapp.com", "pinterest.com", "youtube.com", "google.com",
    "histats.com", "disqus.com", "gravatar.com", "wp.com",
    "doubleclick.net", "adnxs.com", "popads.net", "propellerads.com",
]

DISCARD_HREF_KEYWORDS = [
    "login", "register", "signup", "contact", "about-us", "privacy-policy",
    "dmca", "terms", "faq", "category", "tag", "wp-content", "wp-admin",
    "wp-includes", "xmlrpc", "feed", "comments", "#", "javascript:void",
]

MEDIA_ACTION_KEYWORDS = [
    "download", "mirror", "links", "drive", "cloud", "fast", "direct",
    "pixel", "gdrive", "mega", "stream", "server", "hub", "click", "file",
]


class SemanticHeuristicExtractor:
    """
    Evaluates raw HTML across any website layout and semantically discovers
    download links, quality representations, and stream mirrors.
    """

    def __init__(self, base_url: str = ""):
        self.base_url = base_url

    def score_text_for_media(self, text: str) -> Tuple[float, Dict[str, str]]:
        """
        Scores a snippet of text based on the presence of media tokens.
        Returns confidence score (0.0 - 1.0) and extracted metadata dict.
        """
        score = 0.0
        meta = {
            "quality": "",
            "codec": "",
            "size_str": "",
            "audio": "",
            "season": None,
            "episode": None,
        }

        # Check quality
        for q_regex, q_val in QUALITY_PATTERNS:
            if q_regex.search(text):
                score += 0.35
                if not meta["quality"]:
                    meta["quality"] = q_val
                break

        # Check size
        size_match = SIZE_REGEX.search(text)
        if size_match:
            score += 0.30
            val, unit = size_match.group(1), size_match.group(2).upper()
            meta["size_str"] = f"{val}{unit}"

        # Check codec
        for c_regex, c_val in CODEC_PATTERNS:
            if c_regex.search(text):
                score += 0.15
                if not meta["codec"]:
                    meta["codec"] = c_val
                else:
                    meta["codec"] += f" {c_val}"

        # Check audio
        for a_regex, a_val in AUDIO_PATTERNS:
            if a_regex.search(text):
                score += 0.10
                if not meta["audio"]:
                    meta["audio"] = a_val

        # Check action keywords
        text_lower = text.lower()
        if any(k in text_lower for k in MEDIA_ACTION_KEYWORDS):
            score += 0.10

        # Season / Episode
        se_match = SEASON_EP_REGEX.search(text)
        if se_match:
            if se_match.group(1):
                meta["season"] = int(se_match.group(1))
            if se_match.group(2):
                meta["episode"] = int(se_match.group(2))

        return min(score, 1.0), meta

    def is_valid_media_href(self, href: str) -> bool:
        """Determines whether a link href is a potential media download candidate."""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            return False
        href_lower = href.lower()
        if "drive.google.com" in href_lower or "docs.google.com" in href_lower:
            return True
        if any(bad in href_lower for bad in DISCARD_HREF_KEYWORDS):
            return False
        if any(dom in href_lower for dom in DISCARD_DOMAINS):
            return False
        return True

    def extract_movie_title(self, soup: BeautifulSoup) -> str:
        """Heuristically extracts the cleanest movie/series title from page headers."""
        # 1. og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title_txt = og_title["content"].strip()
            return self._clean_title(title_txt)

        # 2. h1
        h1 = soup.find("h1")
        if h1:
            title_txt = h1.get_text().strip()
            if title_txt:
                return self._clean_title(title_txt)

        # 3. page title
        if soup.title and soup.title.string:
            return self._clean_title(soup.title.string.strip())

        return "Movie"

    def _clean_title(self, raw_title: str) -> str:
        """Strips noise words like Download, Watch Online, Full Movie, etc."""
        cleaned = re.sub(
            r"^(?:Download|Watch\s+Online|Stream)\s+",
            "",
            raw_title,
            flags=re.I,
        )
        # Split on standard separators: ' - ', ' | ', ' – '
        cleaned = re.split(r"\s+[-|–]\s+", cleaned)[0]
        # Remove trailing brackets / quality specs in title
        cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned).strip()
        return cleaned or "Movie"

    def extract_items(self, html: str, base_url: Optional[str] = None) -> List[MediaDownloadItem]:
        """
        Parses full HTML DOM and extracts structured MediaDownloadItem elements.
        Uses structural clustering: links within common headers, buttons, or
        repeating parent blocks inherit metadata from their parent container.
        """
        target_base = base_url or self.base_url
        soup = BeautifulSoup(html, "html.parser")
        movie_name = self.extract_movie_title(soup)
        extracted_items: List[MediaDownloadItem] = []
        seen_urls: Set[str] = set()

        # Step 1: Find all candidate anchors
        candidate_anchors = soup.find_all("a", href=True)

        for a_tag in candidate_anchors:
            raw_href = a_tag["href"].strip()
            if not self.is_valid_media_href(raw_href):
                continue

            full_url = urllib.parse.urljoin(target_base, raw_href)
            if full_url in seen_urls:
                continue

            # Text sources: Anchor text, parent text, ancestor container text
            anchor_text = a_tag.get_text(separator=" ").strip()
            title_attr = a_tag.get("title", "").strip()

            # Climb tree to locate container (e.g. h2, h3, p, div, li, tr)
            parent = a_tag.parent
            container_text = ""
            container_header = ""

            # Check immediate parent
            if parent:
                container_text = parent.get_text(separator=" ").strip()

            # Check higher header ancestor if inside h2/h3/h4
            header_ancestor = a_tag.find_parent(re.compile(r"^h[1-5]$", re.I))
            if header_ancestor:
                container_header = header_ancestor.get_text(separator=" ").strip()

            # Check row/list ancestor (e.g. <tr> or <li> containing specs across columns)
            row_ancestor = a_tag.find_parent(["tr", "li"])
            row_text = ""
            if row_ancestor:
                row_text = row_ancestor.get_text(separator=" ").strip()

            # Check preceding sibling header (e.g. <h3>720p Links</h3> followed by <p><a>Download</a></p>)
            prev_header = ""
            curr = a_tag
            for _ in range(3):
                if not curr:
                    break
                prev_sib = curr.find_previous_sibling(re.compile(r"^h[1-5]$", re.I))
                if prev_sib:
                    prev_header = prev_sib.get_text(separator=" ").strip()
                    break
                curr = curr.parent

            # Combined context for heuristic scoring
            combined_context = f"{anchor_text} {title_attr} {container_text} {row_text} {container_header} {prev_header}"
            score, meta = self.score_text_for_media(combined_context)

            # Heuristic threshold: Must have at least quality OR (size + action keyword) OR score >= 0.35
            is_valid_candidate = (
                score >= 0.35
                or bool(meta["quality"])
                or (bool(meta["size_str"]) and any(k in combined_context.lower() for k in MEDIA_ACTION_KEYWORDS))
                or any(gateway in full_url.lower() for gateway in [
                    "kmhd", "hubcloud", "katdrive", "nexdrive", "magiclinks",
                    "pixeldrain", "sendcm", "1fichier", "streamtape", "streamwish", "gdflix"
                ])
            )

            if not is_valid_candidate:
                continue

            # Fallback quality & codec defaults
            quality = meta["quality"] or "720P"
            codec = meta["codec"] or "X264"
            size_str = meta["size_str"] or "N/A"
            audio = meta["audio"] or "Dual Audio"
            lang = detect_language(f"{combined_context} {movie_name}")

            display_title = f"{codec} {quality}"
            if size_str != "N/A":
                display_title += f" [{size_str}]"

            seen_urls.add(full_url)
            extracted_items.append(
                MediaDownloadItem(
                    title=display_title,
                    movie_name=movie_name,
                    quality=quality,
                    codec=codec,
                    size_str=size_str,
                    audio_info=audio,
                    short_link=full_url,
                    unshortened_landing_url=full_url,
                    season=meta["season"],
                    episode=meta["episode"],
                    language=lang,
                )
            )

        # Sort items by resolution priority: 2160p -> 1080p -> 720p -> 480p
        res_rank = {"2160P": 4, "1080P": 3, "720P": 2, "480P": 1}
        extracted_items.sort(
            key=lambda it: res_rank.get(it.quality.upper(), 0),
            reverse=True,
        )
        return extracted_items

    async def unroll_redirects(
        self,
        items: List[MediaDownloadItem],
        client: httpx.AsyncClient,
        max_hops: int = 3,
        timeout: float = 4.0,
    ) -> List[MediaDownloadItem]:
        """
        Follows initial HTTP redirects (up to max_hops) to discover true target domains
        without running a heavy browser.
        """
        for item in items:
            curr_url = item.short_link
            try:
                for _ in range(max_hops):
                    resp = await client.head(
                        curr_url,
                        headers=DEFAULT_HEADERS,
                        timeout=timeout,
                        follow_redirects=False,
                    )
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("Location")
                        if loc:
                            curr_url = urllib.parse.urljoin(curr_url, loc)
                            continue
                    break
                item.unshortened_landing_url = curr_url
            except Exception:
                # Retain original URL if network or head request fails
                pass
        return items
