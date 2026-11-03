"""
ripper.ripperdb.harvesters.torrent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archetype Harvester for Torrent indexers and aggregators (1337x, YTS, TorrentGalaxy, BitSearch, EZTV).
Extracts release candidates, seeds/leeches counts, magnet links, infohashes,
and un-restricts via Real-Debrid when an API key is configured.
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

logger = logging.getLogger("ripper.ripperdb.harvesters.torrent")

STANDARD_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.bittor.pw:1337/announce",
    "udp://explodie.org:6969/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "udp://tracker.internetwarriors.net:1337/announce",
    "udp://p4p.arenabg.com:1337/announce",
)


def build_magnet_uri(info_hash: str, display_name: str) -> str:
    """Builds a RFC-compliant magnet URI enriched with tier-1 open trackers."""
    clean_hash = re.sub(r"[^a-fA-F0-9]", "", info_hash).lower()
    encoded_name = urllib.parse.quote_plus(display_name)
    trackers = "&".join(f"tr={urllib.parse.quote_plus(tr)}" for tr in STANDARD_TRACKERS)
    return f"magnet:?xt=urn:btih:{clean_hash}&dn={encoded_name}&{trackers}"


class TorrentHarvester(BaseHarvester):
    """Harvester for BitTorrent indexers and trackers."""

    @property
    def archetype(self) -> str:
        return "torrent"

    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Searches torrent indexer using targeted API or standard HTML scraper."""
        low_id = (provider_id + " " + base_url).lower()

        # 1. YTS Dedicated REST API
        if "yts" in low_id:
            yts_results = await self._search_yts(provider_id, base_url, query, year)
            if yts_results:
                return yts_results

        # 2. TorrentGalaxy Specialized Parser
        if "galaxy" in low_id or "tgx" in low_id:
            tgx_results = await self._search_tgx(provider_id, base_url, query, year)
            if tgx_results:
                return tgx_results

        # 3. BitSearch API / Engine
        if "bitsearch" in low_id:
            bs_results = await self._search_bitsearch(provider_id, base_url, query, year)
            if bs_results:
                return bs_results

        # 4. 1337x Specialized Scraper
        if "1337x" in low_id:
            x1337_results = await self._search_1337x(provider_id, base_url, query, year)
            if x1337_results:
                return x1337_results

        # 5. Generic Torrent Search Engine
        return await self._search_generic(provider_id, base_url, query, year)

    async def _search_yts(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Queries YTS official API with mirror failover."""
        mirrors = [
            base_url.rstrip("/"),
            "https://yts.mx",
            "https://yts.pm",
            "https://yts.rs",
            "https://yts.lt",
        ]
        seen_mirrors = set()
        clean_query = urllib.parse.quote_plus(query)

        for mirror in mirrors:
            if mirror in seen_mirrors:
                continue
            seen_mirrors.add(mirror)

            api_url = f"{mirror}/api/v2/list_movies.json?query_term={clean_query}&sort_by=seeds&order_by=desc"
            data = await self.fetch_json(api_url)
            if not data or not isinstance(data, dict):
                continue

            movie_list = (data.get("data") or {}).get("movies")
            if not movie_list or not isinstance(movie_list, list):
                continue

            results: List[ReleaseItem] = []
            for movie in movie_list:
                m_title = movie.get("title", "")
                if not m_title or not is_title_relevant(m_title, query, min_ratio=0.50, query_year=year):
                    continue
                m_year = movie.get("year")
                if year and m_year and year != m_year:
                    continue

                for t in movie.get("torrents", []):
                    t_hash = t.get("hash", "")
                    if not t_hash:
                        continue

                    quality = (t.get("quality") or "1080p").lower()
                    size_str = t.get("size", "")
                    seeds = t.get("seeds", 0)
                    codec = "HEVC" if "x265" in (t.get("type") or "").lower() else "x264"
                    magnet = build_magnet_uri(t_hash, f"{m_title} ({m_year}) [{quality}] [YTS]")
                    q_score = calculate_quality_score(
                        resolution=quality,
                        codec=codec,
                        seeders=seeds,
                    )

                    raw_title = f"{m_title} ({m_year}) [{quality.upper()}] [{size_str}] [YTS]"
                    results.append(
                        ReleaseItem(
                            provider_id=provider_id,
                            raw_title=raw_title,
                            item_url=f"{mirror}/movies/{movie.get('slug', t_hash)}",
                            release_year=m_year,
                            resolution=quality,
                            codec=codec,
                            quality_score=q_score,
                            payload_json=json.dumps({
                                "magnet": magnet,
                                "hash": t_hash,
                                "seeds": seeds,
                                "size": size_str,
                            }),
                        )
                    )

            if results:
                return results

        return []

    async def _search_tgx(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Scrapes TorrentGalaxy for verified releases with seeds and magnets."""
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        tgx_urls = [
            f"{clean_base}/torrents.php?search={encoded_q}&sort=seeders&order=desc",
            f"https://torrentgalaxy.to/torrents.php?search={encoded_q}&sort=seeders&order=desc",
        ]
        results: List[ReleaseItem] = []

        for url in tgx_urls:
            status, html = await self.fetch_text(url)
            if status != 200 or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("div.tgxtablerow")
            for row in rows:
                title_el = row.select_one("a[title][href*='/torrent/']")
                if not title_el:
                    continue

                raw_title = title_el.get("title", "") or title_el.get_text(strip=True)
                if not raw_title or not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                    continue
                magnet_el = row.select_one("a[href^='magnet:?']")
                if not magnet_el:
                    continue

                magnet_url = magnet_el["href"]

                # Extract seeds
                seed_el = row.select_one("span[color='green'], font[color='green'], .tgxtablecell:nth-of-type(11)")
                seeds = 0
                if seed_el:
                    try:
                        seeds = int(re.sub(r"[^\d]", "", seed_el.get_text(strip=True)))
                    except (ValueError, TypeError):
                        pass

                # Resolution
                res = "1080p"
                for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                    if r in raw_title.lower():
                        res = r
                        break

                y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                item_year = int(y_m.group(1)) if y_m else None
                if year and item_year and year != item_year:
                    continue

                q_score = calculate_quality_score(resolution=res, seeders=seeds)
                results.append(
                    ReleaseItem(
                        provider_id=provider_id,
                        raw_title=raw_title,
                        item_url=urllib.parse.urljoin(clean_base, title_el.get("href", "")),
                        release_year=item_year,
                        resolution=res,
                        quality_score=q_score,
                        payload_json=json.dumps({"magnet": magnet_url, "seeds": seeds}),
                    )
                )

            if results:
                break

        return results

    async def _search_bitsearch(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Scrapes BitSearch indexer for torrents with magnet links."""
        clean_base = base_url.rstrip("/") if "bitsearch" in base_url else "https://bitsearch.to"
        encoded_q = urllib.parse.quote_plus(query)
        url = f"{clean_base}/search?q={encoded_q}&sort=seeders"

        status, html = await self.fetch_text(url)
        if status != 200 or not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results: List[ReleaseItem] = []
        cards = soup.select(".card.search-result")

        for card in cards:
            title_el = card.select_one("h5.title a")
            magnet_el = card.select_one("a[href^='magnet:?']")
            if not title_el or not magnet_el:
                continue

            raw_title = title_el.get_text(strip=True)
            if not raw_title or not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                continue
            magnet_url = magnet_el["href"]

            # Seeds
            seeds = 0
            stats = card.select(".stats div")
            for s in stats:
                text = s.get_text(strip=True)
                if "seed" in text.lower() or "arrow-up" in str(s):
                    try:
                        seeds = int(re.sub(r"[^\d]", "", text))
                    except Exception:
                        pass

            res = "1080p"
            for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                if r in raw_title.lower():
                    res = r
                    break

            y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
            item_year = int(y_m.group(1)) if y_m else None
            if year and item_year and year != item_year:
                continue

            results.append(
                ReleaseItem(
                    provider_id=provider_id,
                    raw_title=raw_title,
                    item_url=urllib.parse.urljoin(clean_base, title_el.get("href", "")),
                    release_year=item_year,
                    resolution=res,
                    quality_score=calculate_quality_score(resolution=res, seeders=seeds),
                    payload_json=json.dumps({"magnet": magnet_url, "seeds": seeds}),
                )
            )

        return results

    async def _search_1337x(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Scrapes 1337x movie index with mirror failover."""
        clean_base = base_url.rstrip("/") if "1337x" in base_url else "https://1337x.to"
        encoded_q = urllib.parse.quote_plus(query)
        paths = [
            f"{clean_base}/category-search/{encoded_q}/Movies/1/",
            f"{clean_base}/search/{encoded_q}/1/",
        ]
        results: List[ReleaseItem] = []

        for p in paths:
            status, html = await self.fetch_text(p)
            if status != 200 or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.table-list tbody tr")
            for row in rows:
                name_el = row.select_one("td.name a[href*='/torrent/']")
                if not name_el:
                    continue

                raw_title = name_el.get_text(strip=True)
                if not raw_title or not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                    continue
                href = name_el["href"]
                item_url = urllib.parse.urljoin(clean_base, href)

                seed_el = row.select_one("td.seeds")
                seeds = 0
                if seed_el:
                    try:
                        seeds = int(re.sub(r"[^\d]", "", seed_el.get_text(strip=True)))
                    except Exception:
                        pass

                res = "1080p"
                for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                    if r in raw_title.lower():
                        res = r
                        break

                codec = None
                for c in ["hevc", "x265", "h265", "x264", "h264", "av1"]:
                    if c in raw_title.lower():
                        codec = c.upper()
                        break

                y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                item_year = int(y_m.group(1)) if y_m else None
                if year and item_year and year != item_year:
                    continue

                results.append(
                    ReleaseItem(
                        provider_id=provider_id,
                        raw_title=raw_title,
                        item_url=item_url,
                        release_year=item_year,
                        resolution=res,
                        codec=codec,
                        quality_score=calculate_quality_score(resolution=res, codec=codec, seeders=seeds),
                        payload_json=json.dumps({"seeds": seeds}),
                    )
                )

            if results:
                break

        return results

    async def _search_generic(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """Generic table parser for any BitTorrent indexer."""
        clean_base = base_url.rstrip("/")
        encoded_q = urllib.parse.quote_plus(query)
        search_paths = [
            f"{clean_base}/search/{encoded_q}/1/",
            f"{clean_base}/sort-search/{encoded_q}/seeders/desc/1/",
            f"{clean_base}/search?q={encoded_q}",
            f"{clean_base}/?s={encoded_q}",
        ]
        results: List[ReleaseItem] = []

        for s_url in search_paths:
            status, html = await self.fetch_text(s_url)
            if status != 200 or not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.table-list tbody tr, tr.tgxtablerow, div.search-result")
            for row in rows:
                name_el = row.select_one("td.name a[href*='/torrent/'], a[href*='/torrent/'], a.title")
                if not name_el:
                    continue

                raw_title = name_el.get_text(strip=True)
                if not raw_title or not is_title_relevant(raw_title, query, min_ratio=0.50, query_year=year):
                    continue
                href = name_el.get("href", "")
                item_url = urllib.parse.urljoin(clean_base, href)

                seeds = None
                seed_el = row.select_one("td.seeds, span.seeds, .tgxtablecell:nth-of-type(11)")
                if seed_el:
                    try:
                        seeds = int(re.sub(r"[^\d]", "", seed_el.get_text(strip=True)))
                    except (ValueError, TypeError):
                        pass

                res = "1080p"
                for r in ["2160p", "4k", "1080p", "720p", "480p"]:
                    if r in raw_title.lower():
                        res = r
                        break

                codec = None
                for c in ["hevc", "x265", "h265", "x264", "h264", "av1"]:
                    if c in raw_title.lower():
                        codec = c.upper()
                        break

                y_m = re.search(r"\b(19\d\d|20\d\d)\b", raw_title)
                item_year = int(y_m.group(1)) if y_m else None
                if year and item_year and year != item_year:
                    continue

                q_score = calculate_quality_score(resolution=res, codec=codec, seeders=seeds)
                magnet_el = row.select_one("a[href^='magnet:?']")
                magnet_url = magnet_el["href"] if magnet_el else None

                results.append(
                    ReleaseItem(
                        provider_id=provider_id,
                        raw_title=raw_title,
                        item_url=item_url,
                        release_year=item_year,
                        resolution=res,
                        codec=codec,
                        quality_score=q_score,
                        payload_json=json.dumps({"magnet": magnet_url, "seeds": seeds}) if magnet_url else None,
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
        Extracts magnet link from torrent item, then un-restricts via Real-Debrid
        if an API key is available, returning an unthrottled 4K direct HTTP stream.
        """
        magnet_url = None

        # 1. Check pre-parsed magnet
        if item.payload_json:
            try:
                payload = json.loads(item.payload_json)
                if payload.get("magnet"):
                    magnet_url = payload["magnet"]
            except Exception:
                pass

        # 2. Fetch torrent page and find magnet link
        if not magnet_url:
            status, html = await self.fetch_text(item.item_url)
            if status == 200 and html:
                magnet_match = re.search(r'(magnet:\?[^\s"\'<>]+)', html)
                if magnet_match:
                    magnet_url = magnet_match.group(1)
                else:
                    # Check for infohash in HTML
                    hash_match = re.search(r'\b([0-9a-fA-F]{40})\b', html)
                    if hash_match:
                        magnet_url = build_magnet_uri(hash_match.group(1), item.raw_title)

        if not magnet_url:
            return None

        # 3. Check for Real-Debrid API Key integration
        try:
            from ripper.debrid import RealDebridClient, get_saved_debrid_key
            debrid_key = get_saved_debrid_key()
            if debrid_key:
                client = RealDebridClient(api_key=debrid_key)
                # Attempt cloud unrestriction
                add_res = await client.add_magnet(magnet_url)
                if add_res and add_res.get("id"):
                    t_id = add_res["id"]
                    # Select all files
                    await client.select_all_files(t_id)
                    info = await client.get_torrent_info(t_id)
                    if info and info.get("links"):
                        unrestricted = await client.unrestrict_link(info["links"][0])
                        if unrestricted and unrestricted.stream_url:
                            stream_id = generate_stream_id(item.id, item.resolution or "1080p")
                            return CachedStream(
                                id=stream_id,
                                release_item_id=item.id,
                                direct_url=unrestricted.stream_url,
                                quality=item.resolution or "1080p",
                                expires_at="",
                                is_direct=True,
                                headers={"User-Agent": "Mozilla/5.0"},
                            )
        except Exception as e:
            logger.debug("Real-Debrid unrestrict failed: %s", e)

        # Fallback to direct magnet stream
        stream_id = generate_stream_id(item.id, item.resolution or "1080p")
        return CachedStream(
            id=stream_id,
            release_item_id=item.id,
            direct_url=magnet_url,
            quality=item.resolution or "1080p",
            expires_at="",
            is_direct=False,
        )
