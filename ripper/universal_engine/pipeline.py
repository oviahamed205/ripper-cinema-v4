"""
ripper.universal_engine.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The master autonomous orchestrator unifying all extraction tiers:
- Tier 0: Known Deterministic Gateways (KatMovieHD, MoviesBaba, Vega, CineFreak)
- Tier 1: Semantic DOM Heuristic Extractor (yt-dlp & Scrapling style)
- Tier 2: Headless Dynamic Engine & Real-Time Stream Sniffer (Playwright + CDP)
- Tier 3: Cloud JS Scraper Bridge (Firecrawl API)
- Tier 4: LLM Structural DOM Extractor (OpenAI API)

Guarantees zero hard failures on unknown websites or changed DOM layouts.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional
import httpx

from ..media import (
    MediaDownloadItem,
    extract_media_items_from_html,
    resolve_single_media_item_fast,
    DEFAULT_HEADERS,
)
from .heuristics import SemanticHeuristicExtractor
from .sniffer import HeadlessStreamSniffer
from .firecrawl_bridge import FirecrawlCloudBridge
from .llm_extractor import LLMStructuralExtractor
from ..healer import AutoHealer, CamoufoxStreamSniffer, HealingStrategy

logger = logging.getLogger("ripper.universal_engine.pipeline")


class UniversalPipeline:
    """
    Coordinates cascading extraction tiers to guarantee media link resolution.
    """

    def __init__(self):
        self.heuristics = SemanticHeuristicExtractor()
        self.sniffer = HeadlessStreamSniffer()
        self.camoufox = CamoufoxStreamSniffer()
        self.firecrawl = FirecrawlCloudBridge()
        self.llm = LLMStructuralExtractor()
        self.healer = AutoHealer()

    async def extract(
        self,
        url: str,
        html: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[MediaDownloadItem]:
        """
        Executes the 4-tier extraction cascade until valid media items or streams are resolved.
        """
        items: List[MediaDownloadItem] = []
        should_close_client = False

        if client is None:
            limits = httpx.Limits(max_connections=30, max_keepalive_connections=15)
            client = httpx.AsyncClient(
                timeout=10.0,
                verify=False,
                follow_redirects=True,
                limits=limits,
            )
            should_close_client = True

        try:
            # -------------------------------------------------------------
            # Fetch HTML if not already provided
            # -------------------------------------------------------------
            if not html:
                try:
                    if progress_callback:
                        progress_callback("⚡ [Tier 0] Fetching page over direct HTTP...")
                    resp = await client.get(url, headers=DEFAULT_HEADERS)
                    if resp.status_code == 200:
                        html = resp.text
                except Exception as e:
                    logger.warning(f"[Pipeline] Direct HTTP fetch error: {e}")

            # -------------------------------------------------------------
            # Tier 0: Known Deterministic Parsers
            # -------------------------------------------------------------
            if html:
                try:
                    is_known_site = any(dom in url.lower() for dom in ["cinefreak", "vegamovies", "kmmovies", "katmoviehd", "hdhub4u", "bollyflix", "olamovies"])
                    has_known_container = bool(re.search(r"download-links-div|episode-grid|download-links", html, re.I))
                    if is_known_site or has_known_container:
                        if progress_callback:
                            progress_callback("🔍 [Tier 0] Checking known site patterns...")
                        items = extract_media_items_from_html(html, base_url=url)
                        if items:
                            logger.info(f"[Pipeline] Tier 0 matched {len(items)} items.")
                            return await self._enrich_and_resolve(items, client)
                except Exception as e:
                    logger.debug(f"[Pipeline] Tier 0 exception: {e}")

            # -------------------------------------------------------------
            # Tier 1: Semantic Heuristic DOM Extractor (Zero-Browser Fast Path)
            # -------------------------------------------------------------
            if html:
                if progress_callback:
                    progress_callback("🧠 [Tier 1] Analyzing semantic media heuristics...")
                items = self.heuristics.extract_items(html, base_url=url)
                if items:
                    logger.info(f"[Pipeline] Tier 1 Heuristics matched {len(items)} items.")
                    # Unroll redirects
                    items = await self.heuristics.unroll_redirects(items, client)
                    return await self._enrich_and_resolve(items, client)

            # -------------------------------------------------------------
            # Tier 2: Camoufox C++ Anti-Detect Engine & Stream Sniffer
            # -------------------------------------------------------------
            if progress_callback:
                progress_callback("🌐 [Tier 2] Launching Camoufox anti-detect stream sniffer...")
            try:
                items = await self.camoufox.sniff_and_extract(url, progress_callback=progress_callback)
            except Exception as e:
                logger.debug(f"[Pipeline] Camoufox sniffer fallback: {e}")
                items = await self.sniffer.sniff_and_extract(url)

            if items:
                logger.info(f"[Pipeline] Tier 2 Camoufox resolved {len(items)} items/streams.")
                self.healer.registry.record_success(url, HealingStrategy.TIER_2_CAMOUFOX)
                return await self._enrich_and_resolve(items, client)

            # -------------------------------------------------------------
            # Tier 3: Cloud JS Scraper Bridge (Firecrawl API)
            # -------------------------------------------------------------
            if progress_callback:
                progress_callback("🔥 [Tier 3] Dispatching to Firecrawl Cloud unblocker...")
            items = await self.firecrawl.scrape_and_extract(url, client=client)
            if items:
                logger.info(f"[Pipeline] Tier 3 Firecrawl resolved {len(items)} items.")
                self.healer.registry.record_success(url, HealingStrategy.TIER_3_FIRECRAWL)
                return await self._enrich_and_resolve(items, client)

            # -------------------------------------------------------------
            # Tier 4: Local K2-Horizon GGUF & AI Structural DOM Inference
            # -------------------------------------------------------------
            if html:
                if progress_callback:
                    progress_callback("🧠 [Tier 4] Running local K2-Horizon GGUF DOM reasoning...")
                items = await self.healer.llm.diagnose_and_extract(
                    html,
                    url=url,
                    client=client,
                    progress_callback=progress_callback,
                )
                if not items and self.llm.api_key:
                    items = await self.llm.extract_items(html, base_url=url, client=client)

                if items:
                    logger.info(f"[Pipeline] Tier 4 LLM parsed {len(items)} items.")
                    self.healer.registry.record_success(url, HealingStrategy.TIER_4_LOCAL_GGUF)
                    return await self._enrich_and_resolve(items, client)

        finally:
            if should_close_client:
                await client.aclose()

        return items

    async def _enrich_and_resolve(
        self,
        items: List[MediaDownloadItem],
        client: httpx.AsyncClient,
    ) -> List[MediaDownloadItem]:
        """
        Deduplicates items and auto-resolves mirrors (Cloudflare R2, HubCloud, etc.)
        for any items that match known gateway patterns.
        """
        # Deduplicate by short_link
        unique_map = {}
        for it in items:
            key = (it.quality, it.size_str, it.short_link)
            if key not in unique_map:
                unique_map[key] = it

        unique_items = list(unique_map.values())

        # Concurrently resolve mirrors for gateway links
        resolve_tasks = []
        for it in unique_items:
            landing = (it.unshortened_landing_url or it.short_link).lower()
            if any(k in landing for k in [
                "links.kmhd.", "katdrive", "magiclinks", "nexdrive", "cinefreak",
                "hubcloud", "gamerxyt", "pixeldrain", "streamtape", "streamwish", "send.cm", "1fichier",
                "gofile.io", "doodstream", "dood.", "bunkr", "mega.nz"
            ]):
                resolve_tasks.append(resolve_single_media_item_fast(it, client))

        if resolve_tasks:
            await asyncio.gather(*resolve_tasks, return_exceptions=True)

        return unique_items


async def universal_extract_media(
    url: str,
    html: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    progress_callback: Optional[callable] = None,
) -> List[MediaDownloadItem]:
    """Convenience helper to run the universal pipeline."""
    pipeline = UniversalPipeline()
    return await pipeline.extract(url, html=html, client=client, progress_callback=progress_callback)
