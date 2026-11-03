"""
ripper.ripperdb.harvesters.pstream
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype Harvester for P-Stream instances and forks (Z-Stream, Aether, etc.).
Interacts with P-Stream REST endpoints and client-side stream generators.
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
    DEFAULT_USER_AGENT,
    calculate_quality_score,
    is_title_relevant,
)

logger = logging.getLogger("ripper.ripperdb.harvesters.pstream")


class PStreamHarvester(BaseHarvester):
    """Harvester for P-Stream forks and instances."""

    @property
    def archetype(self) -> str:
        return "pstream"

    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Queries P-Stream REST API or HTML search endpoints."""
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        results: List[ReleaseItem] = []

        # 1. Probe JSON API endpoints
        api_endpoints = [
            f"{clean_base}/api/search?q={encoded_q}",
            f"{clean_base}/api/v1/search?query={encoded_q}",
            f"{clean_base}/api/movies/search?q={encoded_q}",
        ]

        for ep in api_endpoints:
            data = await self.fetch_json(ep)
            if data and isinstance(data, (list, dict)):
                items = data if isinstance(data, list) else data.get("results", data.get("items", []))
                if isinstance(items, list) and items:
                    for entry in items:
                        if not isinstance(entry, dict):
                            continue
                        title = entry.get("title", entry.get("name", ""))
                        if not title:
                            continue

                        # Strict relevance gate
                        if not is_title_relevant(title, query, min_ratio=0.50, query_year=year):
                            continue
                        rel_id = str(entry.get("id", entry.get("slug", "")))
                        rel_year = entry.get("year", entry.get("release_year"))
                        try:
                            rel_year_int = int(rel_year) if rel_year else None
                        except (ValueError, TypeError):
                            rel_year_int = None

                        if year and rel_year_int and year != rel_year_int:
                            continue

                        item_url = f"{clean_base}/watch/{rel_id}" if rel_id else clean_base
                        res = entry.get("resolution", "1080p")
                        q_score = calculate_quality_score(resolution=res, is_direct_cdn=True)

                        results.append(
                            ReleaseItem(
                                provider_id=provider_id,
                                raw_title=f"{title} ({rel_year_int})" if rel_year_int else title,
                                item_url=item_url,
                                release_year=rel_year_int,
                                resolution=res,
                                quality_score=q_score,
                                payload_json=json.dumps({"pstream_id": rel_id, "endpoint": ep}),
                            )
                        )
                    if results:
                        return results

        # 2. Fallback to HTML search page parsing
        html_search_urls = [
            f"{clean_base}/search?q={encoded_q}",
            f"{clean_base}/?s={encoded_q}",
        ]
        for h_url in html_search_urls:
            status, text = await self.fetch_text(h_url)
            if status == 200 and text:
                soup = BeautifulSoup(text, "html.parser")

                # Check for Next.js / Nuxt hydration payload
                next_data = soup.select_one("script#__NEXT_DATA__")
                if next_data and next_data.string:
                    try:
                        n_json = json.loads(next_data.string)
                        page_props = n_json.get("props", {}).get("pageProps", {})
                        items = page_props.get("items", page_props.get("movies", page_props.get("searchResults", [])))
                        if isinstance(items, list):
                            for m in items:
                                m_title = m.get("title", m.get("name", ""))
                                if not m_title:
                                    continue

                                # Strict relevance gate
                                if not is_title_relevant(m_title, query, min_ratio=0.50, query_year=year):
                                    continue
                                m_id = str(m.get("id", m.get("slug", "")))
                                m_year = m.get("year", m.get("release_year"))
                                try:
                                    m_year_int = int(m_year) if m_year else None
                                except (ValueError, TypeError):
                                    m_year_int = None

                                if year and m_year_int and year != m_year_int:
                                    continue

                                item_href = f"{clean_base}/watch/{m_id}" if m_id else clean_base
                                results.append(
                                    ReleaseItem(
                                        provider_id=provider_id,
                                        raw_title=f"{m_title} ({m_year_int})" if m_year_int else m_title,
                                        item_url=item_href,
                                        release_year=m_year_int,
                                        resolution="1080p",
                                        quality_score=calculate_quality_score(resolution="1080p", is_direct_cdn=True),
                                        payload_json=json.dumps({"pstream_id": m_id}),
                                    )
                                )
                            if results:
                                return results
                    except Exception as e:
                        logger.debug("Failed parsing __NEXT_DATA__ on %s: %s", h_url, e)

                cards = soup.select("div.movie-card, a.film-poster, div.search-item, div.film-detail")
                for card in cards:
                    link_tag = card if card.name == "a" else card.find("a")
                    if not link_tag or not link_tag.get("href"):
                        continue
                    item_href = link_tag["href"]
                    if not item_href.startswith("http"):
                        item_href = urllib.parse.urljoin(clean_base, item_href)

                    raw_title = link_tag.get("title") or link_tag.get_text(strip=True)
                    if not raw_title:
                        title_el = card.find(class_=re.compile(r"title|name", re.I))
                        if title_el:
                            raw_title = title_el.get_text(strip=True)

                    if not raw_title:
                        continue

                    # Strict relevance gate
                    if not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                        continue

                    # Extract year if present
                    y_match = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                    card_year = int(y_match.group(1)) if y_match else None
                    if year and card_year and year != card_year:
                        continue

                    if card_year and str(card_year) not in raw_title:
                        raw_title = f"{raw_title} ({card_year})"

                    results.append(
                        ReleaseItem(
                            provider_id=provider_id,
                            raw_title=raw_title,
                            item_url=item_href,
                            release_year=card_year,
                            resolution="1080p",
                            quality_score=calculate_quality_score(resolution="1080p", is_direct_cdn=True),
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
        """Resolves P-Stream player source to direct .m3u8 stream manifest with subtitles."""
        payload = {}
        if item.payload_json:
            try:
                payload = json.loads(item.payload_json)
            except Exception:
                pass

        pstream_id = payload.get("pstream_id")
        clean_base = provider_url.rstrip("/")

        # 1. If we have P-Stream ID, call stream API directly
        if pstream_id:
            stream_api = f"{clean_base}/api/stream/{pstream_id}"
            data = await self.fetch_json(stream_api, headers={"Referer": clean_base})
            if data and isinstance(data, dict):
                stream_url = data.get("stream_url", data.get("url", data.get("src", "")))
                subtitles = data.get("tracks", data.get("subtitles", []))

                if not stream_url and "sources" in data and isinstance(data["sources"], list):
                    for src in data["sources"]:
                        if isinstance(src, dict) and (src.get("file") or src.get("url")):
                            stream_url = src.get("file") or src.get("url")
                            break

                if stream_url:
                    headers = {
                        "Referer": clean_base,
                        "Origin": clean_base,
                        "User-Agent": DEFAULT_USER_AGENT,
                    }
                    if subtitles:
                        headers["subtitles_json"] = json.dumps(subtitles)

                    stream_id = generate_stream_id(item.id, "1080p")
                    return CachedStream(
                        id=stream_id,
                        release_item_id=item.id,
                        direct_url=stream_url,
                        quality="1080p",
                        expires_at="",
                        is_direct=True,
                        headers=headers,
                    )

        # 2. Scrape page HTML for embedded sources or m3u8 playlist regex
        status, html = await self.fetch_text(item.item_url)
        if status == 200 and html:
            m3u8_matches = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m3u8_matches:
                direct = m3u8_matches[0]
                stream_id = generate_stream_id(item.id, "1080p")
                return CachedStream(
                    id=stream_id,
                    release_item_id=item.id,
                    direct_url=direct,
                    quality="1080p",
                    expires_at="",
                    is_direct=True,
                    headers={"Referer": clean_base, "Origin": clean_base, "User-Agent": DEFAULT_USER_AGENT},
                )

        return None
