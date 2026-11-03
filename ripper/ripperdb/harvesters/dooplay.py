"""
ripper.ripperdb.harvesters.dooplay
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype Harvester for WordPress DooPlay themes (VegaMovies, KatMovieHD, CineFreak, etc.).
Parses DooPlay search results, extracts post IDs, triggers doo_player_ajax,
and discovers embedded locker/stream mirrors.
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

logger = logging.getLogger("ripper.ripperdb.harvesters.dooplay")


class DooPlayHarvester(BaseHarvester):
    """Harvester for DooPlay-based WordPress streaming and DDL portals."""

    @property
    def archetype(self) -> str:
        return "dooplay"

    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """
        Searches DooPlay portal using WordPress REST API cascade
        (/wp-json/wp/v2/movies, /wp-json/wp/v2/tvshows, /wp-json/wp/v2/posts)
        with fallback to HTML /?s= search.
        """
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        results: List[ReleaseItem] = []
        seen_links: set[str] = set()

        # 1. WordPress REST API Cascade (Fast JSON with full meta)
        wp_endpoints = [
            f"{clean_base}/wp-json/wp/v2/movies?search={encoded_q}&_embed=1&per_page=15",
            f"{clean_base}/wp-json/wp/v2/tvshows?search={encoded_q}&_embed=1&per_page=15",
            f"{clean_base}/wp-json/wp/v2/posts?search={encoded_q}&_embed=1&per_page=15",
        ]
        for ep in wp_endpoints:
            try:
                posts = await self.fetch_json(ep)
                if posts and isinstance(posts, list):
                    for p in posts:
                        if not isinstance(p, dict):
                            continue
                        p_link = p.get("link", "")
                        if not p_link or p_link in seen_links:
                            continue

                        p_title = (p.get("title") or {}).get("rendered", "")
                        if not p_title:
                            continue

                        # Clean HTML entities from title
                        import html as html_lib
                        p_title = html_lib.unescape(p_title)

                        # Strict relevance gate
                        if not is_title_relevant(p_title, query, min_ratio=0.50, query_year=year):
                            continue

                        y_match = re.search(r"\b(19\d\d|20\d\d)\b", p_title)
                        p_year = int(y_match.group(1)) if y_match else None
                        if year and p_year and year != p_year:
                            continue

                        res = "1080p"
                        for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                            if r in p_title.lower():
                                res = r
                                break

                        seen_links.add(p_link)
                        results.append(
                            ReleaseItem(
                                provider_id=provider_id,
                                raw_title=p_title,
                                item_url=p_link,
                                release_year=p_year,
                                resolution=res,
                                quality_score=calculate_quality_score(resolution=res),
                                payload_json=json.dumps({"wp_post_id": p.get("id")}),
                            )
                        )
                if len(results) >= 5:
                    return results
            except Exception as e:
                logger.debug("WP REST endpoint %s failed: %s", ep, e)

        if results:
            return results

        # 2. HTML Search Fallback /?s=
        search_url = f"{clean_base}/?s={encoded_q}"
        status, html = await self.fetch_text(search_url)
        if status != 200 or not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        # DooPlay standard result container selectors
        articles = soup.select(".result-item article, div.animation-2, article.item-movies, article.item-tvshows")
        if not articles:
            articles = soup.select("div.search-page article, div.items article")

        for art in articles:
            link_tag = art.find("a", href=True)
            if not link_tag:
                continue

            item_url = link_tag["href"]
            if not item_url.startswith("http"):
                item_url = urllib.parse.urljoin(clean_base, item_url)

            title_el = art.select_one(".title a, h3.title, .details .title")
            raw_title = title_el.get_text(strip=True) if title_el else link_tag.get("title") or link_tag.get_text(strip=True)
            if not raw_title:
                continue

            # Strict relevance gate
            if not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                continue

            # Year extraction
            year_el = art.select_one("span.year, .meta span, span.release")
            art_year = None
            if year_el:
                y_m = re.search(r"\b(19\d\d|20\d\d)\b", year_el.get_text())
                if y_m:
                    art_year = int(y_m.group(1))
            if not art_year:
                y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                if y_m:
                    art_year = int(y_m.group(1))

            if year and art_year and year != art_year:
                continue

            # Quality tag
            quality_el = art.select_one(".quality, span.calidad")
            res = quality_el.get_text(strip=True) if quality_el else "1080p"
            q_score = calculate_quality_score(resolution=res)

            # Post ID from class or data attributes
            post_id = None
            class_str = " ".join(art.get("class", []))
            post_id_match = re.search(r"post-(\d+)", class_str)
            if post_id_match:
                post_id = post_id_match.group(1)

            results.append(
                ReleaseItem(
                    provider_id=provider_id,
                    raw_title=raw_title,
                    item_url=item_url,
                    release_year=art_year,
                    resolution=res,
                    quality_score=q_score,
                    payload_json=json.dumps({"dooplay_post_id": post_id}) if post_id else None,
                )
            )

        return results

    async def extract_stream(
        self,
        item: ReleaseItem,
        provider_url: str,
    ) -> Optional[CachedStream]:
        """Extracts direct stream or embedded player from DooPlay post."""
        clean_base = provider_url.rstrip("/")
        status, html = await self.fetch_text(item.item_url)
        if status != 200 or not html:
            return None

        # 1. Look for direct iframe player
        soup = BeautifulSoup(html, "html.parser")
        iframes = soup.select("#playernotice iframe, div.pframe iframe, .play-box iframe, iframe[src*='embed']")
        for iframe in iframes:
            src = iframe.get("src") or iframe.get("data-src")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                stream_id = generate_stream_id(item.id, "1080p")
                return CachedStream(
                    id=stream_id,
                    release_item_id=item.id,
                    direct_url=src,
                    quality="1080p",
                    expires_at="",
                    headers={"Referer": clean_base},
                )

        # 2. Check for doo_player_ajax buttons/elements
        # Format: admin-ajax.php?action=doo_player_ajax&post={id}&nume={nume}&type={type}
        player_buttons = soup.select("ul#playeroptionsul li, .dooplay_player_option")
        for btn in player_buttons:
            post_id = btn.get("data-post")
            nume = btn.get("data-nume")
            p_type = btn.get("data-type", "movie")
            if post_id and nume:
                ajax_url = f"{clean_base}/wp-admin/admin-ajax.php"
                # DooPlay ajax endpoint uses POST or GET with action=doo_player_ajax
                req_url = f"{ajax_url}?action=doo_player_ajax&post={post_id}&nume={nume}&type={p_type}"
                resp_data = await self.fetch_json(req_url, headers={"Referer": item.item_url})
                if resp_data and isinstance(resp_data, dict):
                    embed_url = resp_data.get("embed_url", resp_data.get("url", ""))
                    if not embed_url:
                        # Sometimes returned as HTML iframe snippet in 'html' or 'content'
                        html_snip = resp_data.get("html", resp_data.get("content", ""))
                        if html_snip:
                            m = re.search(r'src=["\']([^"\']+)["\']', html_snip)
                            if m:
                                embed_url = m.group(1)

                    if embed_url:
                        if embed_url.startswith("//"):
                            embed_url = "https:" + embed_url
                        stream_id = generate_stream_id(item.id, "1080p")
                        return CachedStream(
                            id=stream_id,
                            release_item_id=item.id,
                            direct_url=embed_url,
                            quality="1080p",
                            expires_at="",
                            headers={"Referer": clean_base},
                        )

        # 3. Check for Download Box / HubCloud / VCloud locker links
        download_anchors = soup.select(
            ".sbox a, #download a, .links_table a, div.download-links a, a.btn-download"
        )
        for a in download_anchors:
            href = a.get("href", "").strip()
            if not href or href == "#":
                continue
            if any(dom in href.lower() for dom in ["hubcloud", "vcloud", "gamerxyt", "cinecloud", "neodrive"]):
                try:
                    from ripper.resolver.handlers.hubcloud import HubCloudHandler
                    from ripper.resolver.base import ResolutionContext
                    hc = HubCloudHandler()
                    if hc.can_handle(href):
                        ctx = ResolutionContext(target_url=href, hops=[], timeout=self.timeout)
                        hc_res = await hc.resolve(href, client=None, context=ctx)
                        if hc_res and hc_res[0]:
                            stream_id = generate_stream_id(item.id, "1080p")
                            return CachedStream(
                                id=stream_id,
                                release_item_id=item.id,
                                direct_url=hc_res[0],
                                quality="1080p",
                                expires_at="",
                                is_direct=True,
                                headers={"Referer": clean_base, "User-Agent": "Mozilla/5.0"},
                            )
                except Exception as e:
                    logger.debug("HubCloudHandler direct resolution error: %s", e)

                try:
                    from ripper.resolver.engine import ResolverEngine
                    resolver = ResolverEngine()
                    resolved = await resolver.resolve(href)
                    if resolved and resolved.destination_url:
                        stream_id = generate_stream_id(item.id, "1080p")
                        return CachedStream(
                            id=stream_id,
                            release_item_id=item.id,
                            direct_url=resolved.destination_url,
                            quality="1080p",
                            expires_at="",
                            is_direct=True,
                            headers={"Referer": clean_base, "User-Agent": "Mozilla/5.0"},
                        )
                except Exception as e:
                    logger.debug("ResolverEngine failed for DooPlay download link %s: %s", href, e)

        # 4. Check for base64 encoded player sources in scripts or data attributes
        b64_matches = re.findall(r'(?:source|file|player)[\'"]?\s*[:=]\s*[\'"]([A-Za-z0-9+/=]{40,})[\'"]', html)
        for b64_cand in b64_matches:
            try:
                import base64
                decoded = base64.b64decode(b64_cand).decode("utf-8", errors="ignore")
                if "http" in decoded:
                    m = re.search(r'(https?://[^\s"\'<>]+)', decoded)
                    if m:
                        stream_id = generate_stream_id(item.id, "1080p")
                        return CachedStream(
                            id=stream_id,
                            release_item_id=item.id,
                            direct_url=m.group(1),
                            quality="1080p",
                            expires_at="",
                            headers={"Referer": clean_base},
                        )
            except Exception:
                pass

        # 5. Direct .m3u8 regex match on raw page
        m3u8_matches = re.findall(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8_matches:
            stream_id = generate_stream_id(item.id, "1080p")
            return CachedStream(
                id=stream_id,
                release_item_id=item.id,
                direct_url=m3u8_matches[0],
                quality="1080p",
                expires_at="",
                headers={"Referer": clean_base},
            )

        return None
