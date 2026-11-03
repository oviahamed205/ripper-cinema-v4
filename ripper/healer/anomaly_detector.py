"""
ripper.healer.anomaly_detector
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Real-time failure and anomaly detection engine.
Identifies extraction dropouts, Cloudflare Turnstile blocks, rate limits,
DOM mutations, and honeypot/ad-trap poisoning.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..media import MediaDownloadItem
from .models import AnomalyType, ExtractionAnomaly

try:
    from ..resolver.core.honeypot_filter import is_honeypot_url
except ImportError:
    def is_honeypot_url(url: str) -> bool:
        traps = ["vglist.cv", "vegamovies-apk.com", "adsterra", "apk-download", "bestdeal", "clickadu"]
        return any(t in url.lower() for t in traps)

logger = logging.getLogger("ripper.healer.anomaly_detector")

# Fingerprints for Cloudflare Turnstile & Interstitial challenges
CLOUDFLARE_FINGERPRINTS = [
    r"cf-browser-verification",
    r"cf-chl-widget",
    r"challenges\.cloudflare\.com/turnstile",
    r"<title>\s*Just a moment\.\.\.\s*</title>",
    r"Attention Required!\s*\|\s*Cloudflare",
    r"Cloudflare Ray ID:",
    r"Enable JavaScript and cookies to continue",
]

# Known movie & media hosters that should NEVER yield 0 items
KNOWN_MEDIA_HOSTERS = {
    "vegamovies",
    "katmoviehd",
    "hubcloud",
    "nexdrive",
    "fastdl",
    "bollyflix",
    "cinefreak",
    "gdtot",
    "moviesbaba",
    "hdhub4u",
    "olamovies",
    "vcloud",
    "pixeldrain",
}

# Regex to detect suspicious garbage / honeypot titles
GARBAGE_TITLE_REGEX = re.compile(
    r"(?:apk|betting|casino|rummy|download app|install app|ads by|sponsored|porn|dating|winner)",
    re.I,
)


class AnomalyDetector:
    """
    Analyzes raw HTML, HTTP status codes, and extracted media items to identify
    anomalies requiring autonomous self-healing.
    """

    def __init__(self, custom_hosters: Optional[Set[str]] = None):
        self.known_hosters = KNOWN_MEDIA_HOSTERS.union(custom_hosters or set())

    def is_known_media_url(self, url: str) -> bool:
        """Determines if the URL belongs to a known media/streaming portal."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(h in domain for h in self.known_hosters)

    def detect_cloudflare_challenge(self, html: Optional[str], status_code: Optional[int]) -> bool:
        """Checks if response is an active Cloudflare Turnstile / anti-bot interstitial."""
        if status_code in (403, 503) and html:
            for pattern in CLOUDFLARE_FINGERPRINTS:
                if re.search(pattern, html, re.I):
                    return True
        if html and len(html) < 6000:
            for pattern in CLOUDFLARE_FINGERPRINTS:
                if re.search(pattern, html, re.I):
                    return True
        return False

    def check_honeypots(self, items: List[MediaDownloadItem]) -> List[str]:
        """Scans extracted items for blacklisted honeypot / decoy URLs."""
        flagged: List[str] = []
        for it in items:
            candidate_urls = [it.short_link, it.unshortened_landing_url]
            for u in candidate_urls:
                if u and (is_honeypot_url(u) or GARBAGE_TITLE_REGEX.search(it.movie_name or "")):
                    flagged.append(u)
            for m in getattr(it, "servers", []):
                m_url = getattr(m, "direct_download_url", None) or getattr(m, "intermediate_url", "")
                if m_url and is_honeypot_url(m_url):
                    flagged.append(m_url)
        return list(set(flagged))

    def diagnose(
        self,
        url: str,
        html: Optional[str] = None,
        status_code: Optional[int] = None,
        items: Optional[List[MediaDownloadItem]] = None,
        error: Optional[Exception] = None,
    ) -> Optional[ExtractionAnomaly]:
        """
        Runs comprehensive triage across network status, DOM content, and parsed items.
        Returns an ExtractionAnomaly if intervention is warranted, else None.
        """
        items = items or []

        # 1. Check for Rate Limiting
        if status_code == 429 or (html and "too many requests" in html.lower() and len(html) < 2000):
            return ExtractionAnomaly(
                anomaly_type=AnomalyType.RATE_LIMITED,
                url=url,
                status_code=status_code or 429,
                reason="Upstream host returned HTTP 429 Too Many Requests.",
                html_snippet=html[:500] if html else None,
                extracted_items_count=len(items),
            )

        # 2. Check for Cloudflare Turnstile / Anti-Bot Block
        if self.detect_cloudflare_challenge(html, status_code):
            return ExtractionAnomaly(
                anomaly_type=AnomalyType.CLOUDFLARE_BLOCKED,
                url=url,
                status_code=status_code or 403,
                reason="Cloudflare Turnstile or Managed Challenge detected.",
                html_snippet=html[:500] if html else None,
                extracted_items_count=len(items),
            )

        # 3. Check for Honeypot Poisoning
        flagged_traps = self.check_honeypots(items)
        if flagged_traps:
            return ExtractionAnomaly(
                anomaly_type=AnomalyType.HONEYPOT_DETECTED,
                url=url,
                status_code=status_code,
                reason=f"Detected {len(flagged_traps)} honeypot/ad-trap URL(s) in parsed output.",
                html_snippet=html[:500] if html else None,
                extracted_items_count=len(items),
                flagged_urls=flagged_traps,
            )

        # 4. Check for Zero Items on Known Media Hosters
        is_media_host = self.is_known_media_url(url)
        has_media_dom = bool(html and re.search(r"download-links|episode-grid|quality|server|btn-download", html, re.I))

        if len(items) == 0 and (is_media_host or has_media_dom):
            return ExtractionAnomaly(
                anomaly_type=AnomalyType.ZERO_ITEMS,
                url=url,
                status_code=status_code,
                reason="Zero download items extracted on known media portal / mutated DOM layout.",
                html_snippet=html[:500] if html else None,
                extracted_items_count=0,
            )

        # 5. Check for Network Timeout
        if error is not None and ("timeout" in str(error).lower() or "connect" in str(error).lower()):
            return ExtractionAnomaly(
                anomaly_type=AnomalyType.NETWORK_TIMEOUT,
                url=url,
                status_code=status_code,
                reason=f"Network exception encountered: {error}",
                extracted_items_count=len(items),
            )

        return None

    def filter_safe_items(self, items: List[MediaDownloadItem]) -> List[MediaDownloadItem]:
        """
        Strips honeypots, fake ad mirrors, and corrupted items from an item list.
        """
        clean_items: List[MediaDownloadItem] = []
        for it in items:
            if it.short_link and is_honeypot_url(it.short_link):
                continue
            if it.unshortened_landing_url and is_honeypot_url(it.unshortened_landing_url):
                continue
            if it.movie_name and GARBAGE_TITLE_REGEX.search(it.movie_name):
                continue

            # Clean mirrors / servers
            if hasattr(it, "servers"):
                it.servers = [
                    m for m in it.servers
                    if not is_honeypot_url(getattr(m, "direct_download_url", None) or getattr(m, "intermediate_url", ""))
                ]
            clean_items.append(it)

        return clean_items
