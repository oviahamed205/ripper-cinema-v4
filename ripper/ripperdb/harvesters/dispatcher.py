"""
ripper.ripperdb.harvesters.dispatcher
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Federated Harvester Dispatcher.
Coordinates concurrent search execution across multiple archetypes,
deduplicates results, updates ripperdb SQLite storage, and provides
on-demand stream resolution with automatic TTL caching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ripper.ripperdb.cache import (
    CachedStream,
    ReleaseItem,
    RipperDBCache,
    estimate_stream_ttl,
    generate_item_id,
    generate_stream_id,
    normalize_title,
)
from ripper.ripperdb.harvesters.base import (
    BaseHarvester,
    extract_title_and_year,
    is_title_relevant,
)
from ripper.ripperdb.harvesters.ddl import DDLHarvester
from ripper.ripperdb.harvesters.dooplay import DooPlayHarvester
from ripper.ripperdb.harvesters.embed import EmbedHarvester
from ripper.ripperdb.harvesters.pstream import PStreamHarvester
from ripper.ripperdb.harvesters.torrent import TorrentHarvester

logger = logging.getLogger("ripper.ripperdb.harvesters.dispatcher")

VERIFIED_TIER_1_PROVIDERS: List[str] = [
    "cinejoy",
    "rivestream",
    "vegamovies",
    "katmoviehd",
    "kmmovies",
    "hdhub4u",
    "cinefreak",
    "olamovies",
    "flixer",
    "yts",
    "torrentgalaxy",
    "fourkhdhub",
    "4khdhub",
    "moviebox",
    "popcornmovies",
    "zstream",
    "aether",
    "moviesmod",
    "moviesdrive",
    "bollyflix",
    "uwatchfree",
    "lookmovie",
    "1337x",
    "bitsearch",
]

EXCLUDED_NON_STREAMER_DOMAINS: Set[str] = {
    "animecharactersdatabase",
    "arte",
    "7plus",
    "720pier",
    "subtitles",
    "subdl",
    "opensubtitles",
    "addic7ed",
    "tools",
    "wiki",
    "unogs",
    "justwatch",
    "themoviedb",
    "trakt",
    "imdb",
    "senscritique",
    "letterboxd",
    "myanimelist",
    "anilist",
    "simkl",
    "1shows",
    "1max",
}


class HarvesterDispatcher:
    """Central federated dispatcher for all archetype harvesters."""

    def __init__(self, cache_engine: Optional[RipperDBCache] = None):
        self.cache = cache_engine or RipperDBCache()
        self.harvesters: Dict[str, BaseHarvester] = {
            "pstream": PStreamHarvester(),
            "dooplay": DooPlayHarvester(),
            "embed": EmbedHarvester(),
            "torrent": TorrentHarvester(),
            "ddl": DDLHarvester(),
        }
        self.default_harvester = self.harvesters["embed"]

    def register_harvester(self, archetype: str, harvester: BaseHarvester) -> None:
        """Registers or overrides a custom harvester for an archetype."""
        self.harvesters[archetype] = harvester

    def get_harvester(self, archetype: str) -> BaseHarvester:
        """Retrieves harvester for an archetype, falling back to embed harvester."""
        return self.harvesters.get(archetype, self.default_harvester)

    async def search_provider(
        self,
        provider_id: str,
        query: str,
        year: Optional[int] = None,
        timeout: float = 10.0,
    ) -> List[ReleaseItem]:
        """Queries an individual provider using its assigned archetype."""
        prov = self.cache.get_provider(provider_id)
        if not prov:
            logger.warning("Provider %s not found in ripperdb", provider_id)
            return []

        active_mirror = self.cache.get_active_mirror(provider_id) or prov.get("primary_url", "")
        archetype = prov.get("archetype", "embed")
        harvester = self.get_harvester(archetype)

        t0 = time.perf_counter()
        try:
            items = await asyncio.wait_for(
                harvester.search(provider_id, active_mirror, query, year=year),
                timeout=timeout,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            harvester.record_success(elapsed_ms)
            self.cache.update_mirror_latency(provider_id, active_mirror, elapsed_ms)
            return items
        except asyncio.TimeoutError:
            logger.warning("Timeout searching %s (%s)", provider_id, active_mirror)
            harvester.record_failure(TimeoutError("Search timed out"))
            return []
        except Exception as e:
            logger.warning("Error searching %s: %s", provider_id, e)
            harvester.record_failure(e)
            return []

    def get_prioritized_providers(
        self,
        section: Optional[str] = None,
        max_providers: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves active providers prioritized by:
        1. Verified Tier 1 working streaming/torrent portals.
        2. Providers with high health scores and low mirror latencies.
        Filters out non-streaming directories, wikis, and geoblocked networks.
        """
        all_provs = self.cache.list_providers(section=section, active_only=True)
        filtered = []
        for p in all_provs:
            p_id = (p.get("id") or "").lower()
            p_name = (p.get("name") or "").lower()
            p_url = (p.get("primary_url") or "").lower()
            if any(
                ex in p_id or ex in p_name or ex in p_url
                for ex in EXCLUDED_NON_STREAMER_DOMAINS
            ):
                continue
            filtered.append(p)

        tier1_map = {name.lower(): idx for idx, name in enumerate(VERIFIED_TIER_1_PROVIDERS)}

        def sort_key(p: Dict[str, Any]) -> Tuple[int, int, float, str]:
            pid = (p.get("id") or "").lower()
            pname = (p.get("name") or "").lower()
            tier1_rank = 999
            for t1, rank in tier1_map.items():
                if t1 in pid or t1 in pname:
                    tier1_rank = rank
                    break
            is_t1 = 0 if tier1_rank < 999 else 1
            health = int(p.get("health_score") or 100)
            latency = float(p.get("latency_ms") or 999.0)
            return (is_t1, tier1_rank, -health, latency, pid)

        filtered.sort(key=sort_key)
        return filtered[:max_providers]

    async def federated_search(
        self,
        query: str,
        year: Optional[int] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        section: Optional[str] = None,
        min_quality: Optional[str] = None,
        max_providers: int = 30,
        concurrency_limit: int = 10,
        timeout: float = 10.0,
        include_core_scrapers: bool = True,
        on_progress: Optional[Callable[[str, str, int, float], None]] = None,
    ) -> List[ReleaseItem]:
        """
        Executes parallel searches across active cataloged providers.
        Deduplicates, persists release hits to SQLite, and returns sorted results.
        Supports filtering by year, season, episode, section, and quality threshold.
        """
        clean_q = normalize_title(query)
        if not clean_q:
            return []

        search_title = query
        search_year = year
        if search_year is None:
            extracted_title, extracted_year = extract_title_and_year(query)
            if extracted_year is not None:
                search_title = extracted_title
                search_year = extracted_year

        # If TV episode requested, format query
        search_query = search_title
        if season is not None and episode is not None:
            search_query = f"{search_title} S{season:02d}E{episode:02d}"
        elif season is not None:
            search_query = f"{search_title} Season {season}"

        # Fetch prioritized candidate providers from SQLite
        target_provs = self.get_prioritized_providers(section=section, max_providers=max_providers)

        # Core scraper bridge (launches specialized high-speed scrapers)
        core_task = None
        if include_core_scrapers and not section and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from ripper.search import execute_multi_site_search
                core_task = asyncio.create_task(execute_multi_site_search(search_query, timeout=timeout))
            except Exception as e:
                logger.debug("Core multi_site_search bridge unavailable: %s", e)

        semaphore = asyncio.Semaphore(concurrency_limit)

        async def _search_with_sem(prov_dict: Dict[str, Any]) -> List[ReleaseItem]:
            p_id = prov_dict.get("id", "")
            p_name = prov_dict.get("name") or p_id
            t0 = time.perf_counter()
            try:
                async with semaphore:
                    items = await self.search_provider(p_id, search_query, year=search_year, timeout=timeout)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if on_progress:
                    try:
                        on_progress(p_id, p_name, len(items), elapsed_ms)
                    except Exception:
                        pass
                return items
            except Exception as e:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if on_progress:
                    try:
                        on_progress(p_id, p_name, 0, elapsed_ms)
                    except Exception:
                        pass
                return []

        tasks = [_search_with_sem(p) for p in target_provs]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        aggregated: Dict[str, ReleaseItem] = {}
        for res in results_nested:
            if isinstance(res, list):
                for item in res:
                    # Strict title relevance safeguard
                    if not is_title_relevant(item.raw_title, search_title, query_year=search_year):
                        continue

                    # Filter by minimum quality if specified
                    if min_quality:
                        min_q_val = 1080 if "1080" in min_quality else (2160 if "2160" in min_quality or "4k" in min_quality.lower() else 720)
                        item_q_val = 2160 if "2160" in (item.resolution or "").lower() or "4k" in (item.resolution or "").lower() else (1080 if "1080" in (item.resolution or "").lower() else 720)
                        if item_q_val < min_q_val:
                            continue

                    # Deduplicate by unique release item ID
                    if item.id not in aggregated:
                        aggregated[item.id] = item
                    elif item.quality_score > aggregated[item.id].quality_score:
                        aggregated[item.id] = item

        # Integrate results from core multi_site_search
        if core_task:
            try:
                core_res, core_statuses = await core_task
                if on_progress and core_statuses:
                    for st in core_statuses:
                        try:
                            on_progress(st.site_name.lower(), st.site_name, st.result_count, st.latency_ms)
                        except Exception:
                            pass

                for sr in core_res:
                    if not is_title_relevant(sr.title, search_title, query_year=search_year):
                        continue

                    item_yr = None
                    if sr.year and str(sr.year).isdigit():
                        item_yr = int(sr.year)
                    else:
                        _, detected_yr = extract_title_and_year(sr.title)
                        item_yr = detected_yr or search_year

                    c_title = normalize_title(sr.title)
                    c_id = generate_item_id(sr.site_name.lower(), sr.url)
                    prov_id = sr.site_name.lower()
                    if not self.cache.get_provider(prov_id):
                        try:
                            self.cache.upsert_provider(
                                provider_id=prov_id,
                                name=sr.site_name,
                                archetype="embed",
                                primary_url=sr.url,
                                section="streaming",
                            )
                        except Exception:
                            pass
                    rel_item = ReleaseItem(
                        id=c_id,
                        media_id=None,
                        provider_id=prov_id,
                        raw_title=sr.title,
                        clean_title=c_title,
                        item_url=sr.url,
                        release_year=item_yr,
                        resolution=sr.quality_tags or "1080p",
                        codec=None,
                        quality_score=float(sr.relevance_score or 85.0),
                        payload_json=json.dumps({
                            "provider": sr.site_name,
                            "archetype": "core",
                            "url": sr.url,
                            "poster_url": sr.poster_url,
                        }),
                    )
                    if rel_item.id not in aggregated:
                        aggregated[rel_item.id] = rel_item
                    elif rel_item.quality_score > aggregated[rel_item.id].quality_score:
                        aggregated[rel_item.id] = rel_item
            except Exception as e:
                logger.debug("Error aggregating core search results: %s", e)

        items_list = list(aggregated.values())
        if items_list:
            # Batch upsert into SQLite brain
            self.cache.upsert_release_items(items_list)

        # Sort by quality score descending
        items_list.sort(key=lambda x: x.quality_score, reverse=True)
        return items_list

    async def resolve_stream_link(
        self,
        item: ReleaseItem | str,
        timeout: float = 12.0,
    ) -> Optional[CachedStream]:
        """
        High-level stream resolver for ReleaseItem or release ID string.
        Triggers 4-level resolution cascade with timeout and error handling.
        """
        item_id = item.id if isinstance(item, ReleaseItem) else str(item)
        try:
            return await asyncio.wait_for(self.resolve_stream(item_id), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Stream resolution timed out for item %s", item_id)
            return None
        except Exception as e:
            logger.error("Error resolving stream for item %s: %s", item_id, e)
            return None

    async def resolve_stream(self, release_item_id: str) -> Optional[CachedStream]:
        """
        Resolves a release item into a direct stream link via a 4-level cascade:
        - Cache: Instant SQLite stream cache check.
        - Level 0: Targeted Archetype Harvester (PStream, DooPlay, Embed, Torrent, DDL).
        - Level 1: Multi-Provider Gateway & Bypasser (UniversalBypasser, FileLockers, HubCloud).
        - Level 2: Universal Extraction Pipeline (Heuristics, Camoufox, Firecrawl, Local AI).
        - Level 3: Camoufox Stream Sniffer wire-level packet capture.
        """
        # 1. Fast-path: Check existing cached stream in SQLite
        cached = self.cache.get_cached_stream(release_item_id)
        if cached:
            return cached

        # 2. Fetch release item record from SQLite
        item_data = self.cache.get_release_item(release_item_id)
        if not item_data:
            logger.warning("Release item %s not found in ripperdb", release_item_id)
            return None

        provider_id = item_data["provider_id"]
        prov = self.cache.get_provider(provider_id)
        active_mirror = ""
        archetype = "embed"
        if prov:
            active_mirror = self.cache.get_active_mirror(provider_id) or prov.get("primary_url", "")
            archetype = prov.get("archetype", "embed")

        harvester = self.get_harvester(archetype)

        rel_item = ReleaseItem(
            id=item_data["id"],
            media_id=item_data.get("media_id"),
            provider_id=provider_id,
            raw_title=item_data["raw_title"],
            clean_title=item_data["clean_title"],
            item_url=item_data["item_url"],
            release_year=item_data.get("release_year"),
            resolution=item_data.get("resolution"),
            codec=item_data.get("codec"),
            quality_score=item_data.get("quality_score", 0.0),
            payload_json=item_data.get("payload_json"),
        )

        stream: Optional[CachedStream] = None

        # Level 0: Direct Archetype Harvester
        try:
            stream = await harvester.extract_stream(rel_item, active_mirror)
        except Exception as e:
            logger.debug("Level 0 Harvester error for item %s: %s", release_item_id, e)

        # Level 1: Ad-gate bypass / File Locker / HubCloud Resolver Traverse
        if stream and stream.direct_url:
            raw_url = stream.direct_url
            # If not a magnet link and matches resolver/bypasser patterns
            if not raw_url.startswith("magnet:?"):
                try:
                    from ripper.resolver.engine import ResolverEngine
                    resolver = ResolverEngine()
                    resolved = await resolver.resolve(raw_url)
                    if resolved and resolved.destination_url and resolved.destination_url != raw_url:
                        stream.direct_url = resolved.destination_url
                        stream.is_direct = True
                except Exception as e:
                    logger.debug("Level 1 Resolver traversal error: %s", e)

        # Level 2: Universal Pipeline Extraction Fallback
        if not stream or not stream.direct_url:
            try:
                from ripper.universal_engine.pipeline import UniversalPipeline
                pipeline = UniversalPipeline()
                media_items = await pipeline.extract(rel_item.item_url)
                if media_items:
                    best_item = media_items[0]
                    target_url = best_item.direct_download_url
                    if not target_url and best_item.mirrors:
                        target_url = best_item.mirrors[0].url

                    if target_url:
                        stream_id = generate_stream_id(rel_item.id, rel_item.resolution or "1080p")
                        stream = CachedStream(
                            id=stream_id,
                            release_item_id=rel_item.id,
                            direct_url=target_url,
                            quality=best_item.quality or rel_item.resolution or "1080p",
                            expires_at="",
                            is_direct=True,
                            headers={"User-Agent": "Mozilla/5.0", "Referer": rel_item.item_url},
                        )
            except Exception as e:
                logger.debug("Level 2 Universal Pipeline fallback error: %s", e)

        # Level 3: Camoufox Stream Sniffer Wire-Level Packet Capture Fallback
        if not stream or not stream.direct_url:
            try:
                from ripper.healer.camoufox_sniffer import CamoufoxStreamSniffer
                sniffer = CamoufoxStreamSniffer()
                sniffed = await sniffer.sniff_and_extract(rel_item.item_url)
                if sniffed:
                    best_sniff = sniffed[0]
                    sniff_url = best_sniff.direct_download_url or (best_sniff.mirrors[0].url if best_sniff.mirrors else None)
                    if sniff_url:
                        stream_id = generate_stream_id(rel_item.id, rel_item.resolution or "1080p")
                        stream = CachedStream(
                            id=stream_id,
                            release_item_id=rel_item.id,
                            direct_url=sniff_url,
                            quality=best_sniff.quality or rel_item.resolution or "1080p",
                            expires_at="",
                            is_direct=True,
                            headers={"User-Agent": "Mozilla/5.0", "Referer": rel_item.item_url},
                        )
            except Exception as e:
                logger.debug("Level 3 Camoufox Sniffer error: %s", e)

        # Save to stream cache and return
        if stream and stream.direct_url:
            ttl = estimate_stream_ttl(stream.direct_url)
            headers = stream.headers or {}
            if "User-Agent" not in headers:
                headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

            self.cache.set_cached_stream(
                release_item_id=rel_item.id,
                direct_url=stream.direct_url,
                quality=stream.quality or "1080p",
                ttl_seconds=ttl,
                headers=headers,
            )
            return self.cache.get_cached_stream(rel_item.id, quality=stream.quality)

        return None
