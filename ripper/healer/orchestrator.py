"""
ripper.healer.orchestrator
~~~~~~~~~~~~~~~~~~~~~~~~~~

The master autonomous self-healing orchestrator.
Coordinates the 5-strategy cascade with self-learning promotion memory,
guaranteeing media resolution under severe DOM mutations, Cloudflare challenges,
and honeypot traps.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from typing import Callable, List, Optional
import httpx

from ..media import (
    MediaDownloadItem,
    extract_media_items_from_html,
    resolve_single_media_item_fast,
    DEFAULT_HEADERS,
)
from .anomaly_detector import AnomalyDetector
from .camoufox_sniffer import CamoufoxStreamSniffer
from .dom_pruner import DOMPruner
from .dynamic_registry import DynamicRegistry
from .llm_dom_diagnostics import LLMDiagnostics
from .models import (
    AnomalyType,
    HealedResult,
    HealerConfig,
    HealingStrategy,
)

logger = logging.getLogger("ripper.healer.orchestrator")


class AutoHealer:
    """
    Central self-healing coordinator. Combines persistent memory, stealth Camoufox sniffing,
    Firecrawl cloud unblocking, and local GGUF reasoning into a fault-tolerant extraction loop.
    """

    def __init__(self, config: Optional[HealerConfig] = None):
        self.config = config or HealerConfig()
        self.registry = DynamicRegistry(self.config.registry_file)
        self.detector = AnomalyDetector()
        self.sniffer = CamoufoxStreamSniffer(self.config)
        self.llm = LLMDiagnostics(self.config)

    async def heal(
        self,
        url: str,
        html: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> HealedResult:
        """
        Executes the self-healing cascade against the target URL.
        Returns a HealedResult with resolved items and performance metadata.
        """
        start_time = time.time()
        should_close_client = False

        if client is None:
            client = httpx.AsyncClient(
                timeout=10.0,
                verify=False,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
            should_close_client = True

        try:
            # -----------------------------------------------------------------
            # Step 0: Check Domain Aliasing / Mirror Redirection
            # -----------------------------------------------------------------
            active_url = url
            domain = self.registry.extract_domain(url)
            alias_domain = self.registry.get_domain_alias(domain)
            if alias_domain != domain:
                active_url = url.replace(domain, alias_domain)
                logger.info(f"[AutoHealer] Rerouted {domain} -> {alias_domain} ({active_url})")

            # -----------------------------------------------------------------
            # Step 1: Initial Page Fetch & Fast-Path Triage
            # -----------------------------------------------------------------
            status_code = None
            if not html:
                try:
                    if progress_callback:
                        progress_callback("⚡ [Tier 1] Fetching target page via direct HTTP...")
                    resp = await client.get(active_url, headers=DEFAULT_HEADERS)
                    status_code = resp.status_code
                    if status_code == 200:
                        html = resp.text
                    elif resp.is_redirect or resp.status_code in (301, 302, 307):
                        new_loc = resp.headers.get("location", "")
                        if new_loc:
                            new_domain = self.registry.extract_domain(new_loc)
                            if new_domain and new_domain != domain:
                                self.registry.map_domain_alias(domain, new_domain)
                                active_url = new_loc
                except Exception as e:
                    logger.debug(f"[AutoHealer] Direct fetch notice: {e}")

            # Run deterministic extraction
            items: List[MediaDownloadItem] = []
            if html:
                items = extract_media_items_from_html(html, base_url=active_url)
                items = self.detector.filter_safe_items(items)

            # Diagnose extraction output
            anomaly = self.detector.diagnose(
                url=active_url,
                html=html,
                status_code=status_code,
                items=items,
            )

            # Fast-path exit if extraction is completely healthy
            if not anomaly and items:
                elapsed_ms = (time.time() - start_time) * 1000.0
                return HealedResult(
                    success=True,
                    items=items,
                    strategy_used=HealingStrategy.TIER_1_HEURISTICS,
                    latency_ms=elapsed_ms,
                )

            # -----------------------------------------------------------------
            # Step 2: Self-Healing Cascade Activation
            # -----------------------------------------------------------------
            if anomaly:
                logger.info(f"[AutoHealer] Triggering healing cascade. Reason: {anomaly.reason}")
                if progress_callback:
                    progress_callback(f"🛡️ [AutoHealer] Flagged {anomaly.anomaly_type.value}: {anomaly.reason}")

            # Check if domain has a previously promoted winning strategy
            promoted = self.registry.get_promoted_strategies(active_url)
            logger.debug(f"[AutoHealer] Promoted strategies for {domain}: {[s.value for s in promoted]}")

            # Strategy Order: Promoted strategy first, then standard cascade
            strategies_to_try = []
            for s in promoted:
                if s not in strategies_to_try:
                    strategies_to_try.append(s)

            default_cascade = [
                HealingStrategy.TIER_2_CAMOUFOX,
                HealingStrategy.TIER_3_FIRECRAWL,
                HealingStrategy.TIER_4_LOCAL_GGUF,
            ]
            for s in default_cascade:
                if s not in strategies_to_try:
                    strategies_to_try.append(s)

            for strat in strategies_to_try:
                # -------------------------------------------------------------
                # Tier 2: Camoufox C++ Anti-Detect Wire Sniffer
                # -------------------------------------------------------------
                if strat == HealingStrategy.TIER_2_CAMOUFOX:
                    if progress_callback:
                        progress_callback("🌐 [Healer] Tier 2: Camoufox stealth browser sniffer active...")
                    try:
                        sniffed_items = await self.sniffer.sniff_and_extract(
                            active_url,
                            progress_callback=progress_callback,
                        )
                        sniffed_items = self.detector.filter_safe_items(sniffed_items)
                        if sniffed_items:
                            elapsed_ms = (time.time() - start_time) * 1000.0
                            self.registry.record_success(domain, strat, elapsed_ms)
                            return HealedResult(
                                success=True,
                                items=sniffed_items,
                                strategy_used=strat,
                                latency_ms=elapsed_ms,
                                cached_to_registry=True,
                            )
                    except Exception as e:
                        logger.warning(f"[AutoHealer] Tier 2 Camoufox exception: {e}")

                # -------------------------------------------------------------
                # Tier 3: Firecrawl Cloud Unblocker
                # -------------------------------------------------------------
                elif strat == HealingStrategy.TIER_3_FIRECRAWL:
                    if self.config.firecrawl_api_key:
                        if progress_callback:
                            progress_callback("🔥 [Healer] Tier 3: Dispatching to Firecrawl Cloud unblocker...")
                        try:
                            from ..universal_engine.firecrawl_bridge import FirecrawlCloudBridge
                            bridge = FirecrawlCloudBridge(api_key=self.config.firecrawl_api_key)
                            cloud_items = await bridge.scrape_and_extract(active_url, client=client)
                            cloud_items = self.detector.filter_safe_items(cloud_items)
                            if cloud_items:
                                elapsed_ms = (time.time() - start_time) * 1000.0
                                self.registry.record_success(domain, strat, elapsed_ms)
                                return HealedResult(
                                    success=True,
                                    items=cloud_items,
                                    strategy_used=strat,
                                    latency_ms=elapsed_ms,
                                    cached_to_registry=True,
                                )
                        except Exception as e:
                            logger.warning(f"[AutoHealer] Tier 3 Firecrawl exception: {e}")

                # -------------------------------------------------------------
                # Tier 4: Local GGUF DOM Reasoning
                # -------------------------------------------------------------
                elif strat in (HealingStrategy.TIER_4_LOCAL_GGUF, HealingStrategy.TIER_4_CLOUD_LLM):
                    if html:
                        if progress_callback:
                            progress_callback("🧠 [Healer] Tier 4: Local K2-Horizon GGUF DOM reasoning...")
                        try:
                            llm_items = await self.llm.diagnose_and_extract(
                                html,
                                url=active_url,
                                client=client,
                                progress_callback=progress_callback,
                            )
                            llm_items = self.detector.filter_safe_items(llm_items)
                            if llm_items:
                                elapsed_ms = (time.time() - start_time) * 1000.0
                                self.registry.record_success(domain, strat, elapsed_ms)
                                return HealedResult(
                                    success=True,
                                    items=llm_items,
                                    strategy_used=strat,
                                    latency_ms=elapsed_ms,
                                    cached_to_registry=True,
                                )
                        except Exception as e:
                            logger.warning(f"[AutoHealer] Tier 4 LLM exception: {e}")

        finally:
            if should_close_client:
                await client.aclose()

        elapsed_ms = (time.time() - start_time) * 1000.0
        return HealedResult(
            success=len(items) > 0,
            items=items,
            strategy_used=None,
            latency_ms=elapsed_ms,
            details={"anomaly": anomaly.to_dict() if anomaly else None},
        )


def self_healing_extract(func: Callable):
    """
    Decorator wrapping extraction calls with the AutoHealer autonomous cascade.
    """
    @functools.wraps(func)
    async def wrapper(url: str, *args, **kwargs):
        # 1. Run primary function
        try:
            items = await func(url, *args, **kwargs) if inspect.iscoroutinefunction(func) else func(url, *args, **kwargs)
            if items:
                detector = AnomalyDetector()
                if not detector.check_honeypots(items):
                    return items
        except Exception:
            pass

        # 2. Trigger AutoHealer
        healer = AutoHealer()
        result = await healer.heal(url)
        return result.items

    return wrapper
