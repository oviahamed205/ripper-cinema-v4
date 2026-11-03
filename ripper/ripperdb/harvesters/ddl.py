"""
ripper.ripperdb.harvesters.ddl
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype Harvester for Direct Download Link (DDL) portals and cyberlockers.
Discovers download buttons, automatically dissolves adgates & shorteners via UniversalBypasserEngine,
unrolls containers (Filecrypt/Keeplinks), and extracts direct streams via FileLockersHandler (PixelDrain, GoFile, MediaFire, KrakenFiles).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ripper.ripperdb.cache import (
    CachedStream,
    ReleaseItem,
    estimate_stream_ttl,
    generate_item_id,
    generate_stream_id,
    normalize_title,
)
from ripper.ripperdb.harvesters.base import (
    BaseHarvester,
    calculate_quality_score,
    is_title_relevant,
)

logger = logging.getLogger("ripper.ripperdb.harvesters.ddl")

KNOWN_LOCKER_DOMAINS = (
    "pixeldrain.com",
    "pixeldrain.dev",
    "gofile.io",
    "qiwi.gg",
    "mediafire.com",
    "1fichier.com",
    "mega.nz",
    "rapidgator.net",
    "krakenfiles.com",
    "send.cm",
    "racaty.net",
    "racaty.io",
    "hubcloud.",
    "vcloud.",
    "katdrive.",
    "appdrive.",
    "gdtot.",
)

KNOWN_CONTAINER_DOMAINS = (
    "filecrypt.cc",
    "filecrypt.to",
    "filecrypt.co",
    "keeplinks.org",
    "keeplinks.co",
    "pastebin.com",
)

KNOWN_ADGATE_DOMAINS = (
    "droplink.",
    "gplinks.",
    "rocklinks.",
    "ouo.io",
    "ouo.press",
    "sub2unlock.",
    "shareus.",
    "shrinkearn.",
    "linkvertise.",
    "adfly.",
    "try2link.",
    "bstlar.",
    "psa.wf",
    "paster.so",
)


class DDLHarvester(BaseHarvester):
    """Harvester for DDL portals and fast cyberlockers."""

    @property
    def archetype(self) -> str:
        return "ddl"

    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Searches DDL portal for matching releases."""
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        search_urls = [
            f"{clean_base}/?s={encoded_q}",
            f"{clean_base}/search?q={encoded_q}",
            f"{clean_base}/search/{encoded_q}",
            f"{clean_base}/page/1/?s={encoded_q}",
        ]
        results: List[ReleaseItem] = []
        seen_urls: set[str] = set()

        for s_url in search_urls:
            status, html = await self.fetch_text(s_url)
            if status != 200 or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            entries = soup.select(
                "article.post, .entry-title a, h2.title a, .post-item a, "
                "div.search-result a, div.blog-post, div.post-content a, "
                ".result-item a"
            )

            for entry in entries:
                link_tag = entry if entry.name == "a" else entry.find("a", href=True)
                if not link_tag or not link_tag.get("href"):
                    continue

                item_url = link_tag["href"]
                if not item_url.startswith("http"):
                    item_url = urllib.parse.urljoin(clean_base, item_url)

                if item_url in seen_urls:
                    continue

                raw_title = link_tag.get("title") or link_tag.get_text(strip=True)
                if not raw_title or len(raw_title) < 2:
                    continue

                # Strict relevance gate
                if not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                    continue

                # Skip non-content navigation links
                if any(skip in item_url.lower() for skip in ["/category/", "/tag/", "/author/", "/page/", "/feed"]):
                    continue

                # Year detection
                y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                item_year = int(y_m.group(1)) if y_m else None
                if year and item_year and year != item_year:
                    continue

                # Resolution detection
                res = "1080p"
                for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                    if r in raw_title.lower():
                        res = r
                        break

                q_score = calculate_quality_score(resolution=res, is_direct_cdn=True)

                seen_urls.add(item_url)
                results.append(
                    ReleaseItem(
                        provider_id=provider_id,
                        raw_title=raw_title,
                        item_url=item_url,
                        release_year=item_year,
                        resolution=res,
                        quality_score=q_score,
                    )
                )

            if results:
                break

        return results

    async def extract_stream(
        self,
        item: ReleaseItem,
        provider_url: str,
    ) -> Optional[CachedStream]:
        """
        Scrapes DDL post, automatically bypasses ad-shorteners via UniversalBypasserEngine,
        unrolls Filecrypt/Keeplinks containers, and resolves direct cyberlocker streams
        (PixelDrain, GoFile, MediaFire, KrakenFiles) via FileLockersHandler.
        """
        clean_base = provider_url.rstrip("/")
        status, html = await self.fetch_text(item.item_url)
        if status != 200 or not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)

        candidate_urls: List[str] = []
        for a in links:
            href = a["href"].strip()
            if not href.startswith("http") or href == item.item_url:
                continue

            low_href = href.lower()

            # 1. Container link (Filecrypt, Keeplinks, Pastebin)
            if any(c in low_href for c in KNOWN_CONTAINER_DOMAINS):
                candidate_urls.append(href)
            # 2. Known ad-gate shortener (Droplink, GPLinks, Rocklinks, Ouo, etc.)
            elif any(g in low_href for g in KNOWN_ADGATE_DOMAINS):
                candidate_urls.append(href)
            # 3. Direct cyberlocker link
            elif any(d in low_href for d in KNOWN_LOCKER_DOMAINS):
                candidate_urls.append(href)
            # 4. Download buttons with target keyword
            elif any(k in a.get_text().lower() for k in [
                "download", "fast server", "pixeldrain", "gofile", "mediafire",
                "direct link", "cloud download", "1fichier"
            ]):
                candidate_urls.append(href)

        if not candidate_urls:
            # Check for direct video/archive file extensions
            for a in links:
                href = a["href"].strip()
                if any(href.lower().endswith(ext) for ext in [".mkv", ".mp4", ".zip", ".rar"]):
                    candidate_urls.append(href)

        if not candidate_urls:
            return None

        # Process candidates through Universal Bypasser & File Locker resolution
        for candidate in candidate_urls:
            resolved_url = await self._resolve_target(candidate)
            if resolved_url:
                stream_id = generate_stream_id(item.id, item.resolution or "1080p")
                return CachedStream(
                    id=stream_id,
                    release_item_id=item.id,
                    direct_url=resolved_url,
                    quality=item.resolution or "1080p",
                    expires_at="",
                    is_direct=True,
                    headers={"Referer": clean_base, "User-Agent": "Mozilla/5.0"},
                )

        return None

    async def _resolve_target(self, url: str) -> Optional[str]:
        """Traverses adgates, unrolls containers, and extracts direct locker stream URLs."""
        current_url = url

        # 1. Container Unrolling (Filecrypt, Keeplinks)
        if any(c in current_url.lower() for c in KNOWN_CONTAINER_DOMAINS):
            try:
                from ripper.universal_bypasser.engine import UniversalBypasserEngine
                bypasser = UniversalBypasserEngine()
                c_res = await bypasser.unroll_container(current_url)
                if c_res and c_res.extracted_links:
                    current_url = c_res.extracted_links[0]
            except Exception as e:
                logger.debug("Container unroll error for %s: %s", current_url, e)

        # 2. Ad-Gate Dissolution (Droplink, GPLinks, Rocklinks, Ouo, etc.)
        if any(g in current_url.lower() for g in KNOWN_ADGATE_DOMAINS):
            try:
                from ripper.universal_bypasser.engine import UniversalBypasserEngine
                bypasser = UniversalBypasserEngine()
                b_res = await bypasser.bypass_shortlink(current_url)
                if b_res and b_res.resolved_url:
                    current_url = b_res.resolved_url
            except Exception as e:
                logger.debug("Ad-gate bypass error for %s: %s", current_url, e)

        # 3. Direct File Locker Extraction (PixelDrain, GoFile, MediaFire, KrakenFiles)
        low = current_url.lower()

        # PixelDrain API conversion
        if "pixeldrain.com" in low or "pixeldrain.dev" in low:
            m = re.search(r"pixeldrain\.(?:com|dev)/(?:u|l)/([a-zA-Z0-9_-]+)", current_url)
            if m:
                return f"https://pixeldrain.com/api/file/{m.group(1).strip('/')}?download"

        # Resolver Engine / FileLockersHandler resolution
        try:
            from ripper.resolver.engine import ResolverEngine
            resolver = ResolverEngine()
            res = await resolver.resolve(current_url)
            if res and res.destination_url:
                return res.destination_url
        except Exception as e:
            logger.debug("ResolverEngine traversal error for %s: %s", current_url, e)

        return current_url if current_url.startswith("http") else None

