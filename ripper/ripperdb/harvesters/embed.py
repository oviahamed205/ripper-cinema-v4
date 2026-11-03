"""
ripper.ripperdb.harvesters.embed
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype Harvester for multi-server embed aggregators (Cinejoy, Rive, CorsFlix,
VidPlay, StreamWish, FileLions, Hexa, Stellar, etc.).
Extracts embedded player iframes, unpacks obfuscated JS (Dean Edwards Packer),
and returns direct playable stream URLs.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ripper.resolver.core.packer_unpack import detect_packed, unpack_packer
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

logger = logging.getLogger("ripper.ripperdb.harvesters.embed")


class EmbedHarvester(BaseHarvester):
    """Harvester for multi-server embed streaming providers."""

    @property
    def archetype(self) -> str:
        return "embed"

    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Searches embed aggregator for target movie or series."""
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        results: List[ReleaseItem] = []
        seen_urls: set[str] = set()

        search_urls = [
            f"{clean_base}/search?keyword={encoded_q}",
            f"{clean_base}/search?q={encoded_q}",
            f"{clean_base}/search/{encoded_q}",
            f"{clean_base}/?s={encoded_q}",
        ]

        for s_url in search_urls:
            status, html = await self.fetch_text(s_url)
            if status != 200 or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            # Common card selectors on modern movie streaming aggregators
            cards = soup.select(
                ".flw-item, .film-item, .movie-item, .film_list-wrap .film-poster, "
                ".search-result-item, .item-movie, .item"
            )

            for card in cards:
                link_tag = card if card.name == "a" else card.find("a", href=True)
                if not link_tag:
                    continue

                item_href = link_tag["href"]
                if not item_href.startswith("http"):
                    item_href = urllib.parse.urljoin(clean_base, item_href)

                raw_title = link_tag.get("title") or link_tag.get_text(strip=True)
                if not raw_title:
                    title_el = card.find(class_=re.compile(r"title|name|film-name", re.I))
                    if title_el:
                        raw_title = title_el.get_text(strip=True)

                if not raw_title or len(raw_title) < 2:
                    continue

                # Precision relevance gate: Reject sidebar / popular / unrelated cards
                if not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                    continue

                # Year parsing
                year_el = card.find(class_=re.compile(r"fdi-item|year|date", re.I))
                item_year = None
                if year_el:
                    y_m = re.search(r"\b(19\d\d|20\d\d)\b", year_el.get_text())
                    if y_m:
                        item_year = int(y_m.group(1))
                if not item_year:
                    y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                    if y_m:
                        item_year = int(y_m.group(1))

                if year and item_year and year != item_year:
                    continue

                if item_year and str(item_year) not in raw_title:
                    raw_title = f"{raw_title} ({item_year})"

                # Resolution detection
                res_el = card.find(class_=re.compile(r"quality|fdi-quality", re.I))
                res = res_el.get_text(strip=True) if res_el else "1080p"
                q_score = calculate_quality_score(resolution=res)

                if item_href not in seen_urls:
                    seen_urls.add(item_href)
                    results.append(
                        ReleaseItem(
                            provider_id=provider_id,
                            raw_title=raw_title,
                            item_url=item_href,
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
        Extracts stream from page by recursively traversing iframe embed players,
        unpacking Dean Edwards Packer JS, resolving via VideoHostsHandler / AnyStreamEngine,
        and extracting WebVTT/SRT subtitles.
        """
        clean_base = provider_url.rstrip("/")
        status, html = await self.fetch_text(item.item_url)
        if status != 200 or not html:
            return None

        # 1. Check for Dean Edwards packed scripts in parent page
        if detect_packed(html):
            try:
                unpacked = unpack_packer(html)
                m3u8_matches = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', unpacked)
                if m3u8_matches:
                    subtitles = self._extract_subtitles(html, clean_base)
                    stream_id = generate_stream_id(item.id, "1080p")
                    headers = {"Referer": clean_base, "Origin": clean_base, "User-Agent": "Mozilla/5.0"}
                    if subtitles:
                        headers["X-Subtitles"] = json.dumps(subtitles)
                    return CachedStream(
                        id=stream_id,
                        release_item_id=item.id,
                        direct_url=m3u8_matches[0],
                        quality="1080p",
                        expires_at="",
                        is_direct=True,
                        headers=headers,
                    )
            except Exception as e:
                logger.debug("Parent page packer unpack failed: %s", e)

        # 2. Extract and resolve all iframe players (recursively up to 3 levels)
        iframes = await self._find_iframes_recursive(html, item.item_url, max_depth=3)

        for src in iframes:
            # 2a. Specialized VideoHostsHandler resolution (DoodStream, MixDrop, StreamWish, Voe, Filemoon, etc.)
            try:
                from ripper.resolver.handlers.video_hosts import VideoHostsHandler
                from ripper.resolver.base import ResolutionContext
                vh_handler = VideoHostsHandler()
                if vh_handler.can_handle(src):
                    ctx = ResolutionContext(target_url=src, hops=[], timeout=self.timeout)
                    vh_res = await vh_handler.resolve(src, client=None, context=ctx)
                    if vh_res and vh_res[0]:
                        direct_video = vh_res[0]
                        stream_id = generate_stream_id(item.id, "1080p")
                        return CachedStream(
                            id=stream_id,
                            release_item_id=item.id,
                            direct_url=direct_video,
                            quality="1080p",
                            expires_at="",
                            is_direct=True,
                            headers={"Referer": src, "User-Agent": "Mozilla/5.0"},
                        )
            except Exception as e:
                logger.debug("VideoHostsHandler check failed for %s: %s", src, e)

            # 2b. AnyStream Engine resolution (StreamTape, FileLions, etc.)
            try:
                from ripper.anystream.engine import AnyStreamEngine
                as_engine = AnyStreamEngine()
                as_res = await as_engine.resolve(src)
                if as_res and as_res.stream_url:
                    stream_id = generate_stream_id(item.id, as_res.quality or "1080p")
                    return CachedStream(
                        id=stream_id,
                        release_item_id=item.id,
                        direct_url=as_res.stream_url,
                        quality=as_res.quality or "1080p",
                        expires_at="",
                        is_direct=True,
                        headers={"Referer": src, "User-Agent": "Mozilla/5.0"},
                    )
            except Exception as e:
                logger.debug("AnyStreamEngine check failed for %s: %s", src, e)

            # 2c. Fetch iframe content, unpack, and parse for direct streams & subtitles
            try:
                if_status, if_html = await self.fetch_text(src, headers={"Referer": item.item_url})
                if if_status == 200 and if_html:
                    unpacked_content = unpack_packer(if_html) if detect_packed(if_html) else if_html
                    m_urls = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', unpacked_content)
                    if not m_urls:
                        m_urls = re.findall(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', unpacked_content)

                    if m_urls:
                        parsed_src = urllib.parse.urlparse(src)
                        origin = f"{parsed_src.scheme}://{parsed_src.netloc}"
                        subtitles = self._extract_subtitles(unpacked_content, origin)
                        headers = {"Referer": src, "Origin": origin, "User-Agent": "Mozilla/5.0"}
                        if subtitles:
                            headers["X-Subtitles"] = json.dumps(subtitles)

                        stream_id = generate_stream_id(item.id, "1080p")
                        return CachedStream(
                            id=stream_id,
                            release_item_id=item.id,
                            direct_url=m_urls[0],
                            quality="1080p",
                            expires_at="",
                            is_direct=True,
                            headers=headers,
                        )
            except Exception as e:
                logger.debug("Iframe fetch & unpack error for %s: %s", src, e)

        # 3. Direct .m3u8 regex on page
        page_m3u8 = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if page_m3u8:
            stream_id = generate_stream_id(item.id, "1080p")
            return CachedStream(
                id=stream_id,
                release_item_id=item.id,
                direct_url=page_m3u8[0],
                quality="1080p",
                expires_at="",
                is_direct=True,
                headers={"Referer": clean_base, "Origin": clean_base, "User-Agent": "Mozilla/5.0"},
            )

        # 4. Fallback to top-level iframe if found
        if iframes:
            stream_id = generate_stream_id(item.id, "1080p")
            return CachedStream(
                id=stream_id,
                release_item_id=item.id,
                direct_url=iframes[0],
                quality="1080p",
                expires_at="",
                is_direct=False,
                headers={"Referer": item.item_url, "User-Agent": "Mozilla/5.0"},
            )

        return None

    async def _find_iframes_recursive(
        self,
        html: str,
        current_url: str,
        max_depth: int = 3,
        current_depth: int = 0,
    ) -> List[str]:
        """Recursively discovers iframe player links up to max_depth."""
        found_urls: List[str] = []
        if current_depth >= max_depth:
            return found_urls

        soup = BeautifulSoup(html, "html.parser")
        iframes = soup.select(
            "iframe[src], iframe[data-src], #iframe-embed, .play-box iframe, div.player iframe"
        )
        for iframe in iframes:
            src = iframe.get("src") or iframe.get("data-src")
            if not src or src.startswith("about:") or src.startswith("javascript:"):
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif not src.startswith("http"):
                src = urllib.parse.urljoin(current_url, src)

            found_urls.append(src)

            # Recurse one level if not at max_depth
            if current_depth + 1 < max_depth:
                try:
                    s, sub_html = await self.fetch_text(src, headers={"Referer": current_url})
                    if s == 200 and sub_html:
                        sub_iframes = await self._find_iframes_recursive(
                            sub_html, src, max_depth, current_depth + 1
                        )
                        found_urls.extend(sub_iframes)
                except Exception:
                    pass

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for u in found_urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    def _extract_subtitles(self, html: str, base_url: str) -> List[Dict[str, str]]:
        """Extracts subtitle track definitions from HTML `<track>` tags or JS blobs."""
        subs: List[Dict[str, str]] = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            for t in soup.select("track[kind='subtitles'], track[kind='captions']"):
                src = t.get("src")
                if not src:
                    continue
                if not src.startswith("http"):
                    src = urllib.parse.urljoin(base_url, src)
                lang = t.get("srclang") or t.get("label") or "en"
                subs.append({"file": src, "label": lang, "kind": "captions"})
        except Exception:
            pass
        return subs
