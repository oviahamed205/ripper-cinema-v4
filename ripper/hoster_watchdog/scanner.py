"""
ripper.hoster_watchdog.scanner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

High-concurrency async health scanner for hosting providers and movie mirrors.
Pings mirrors, measures latency, detects HTTP 301/308 domain transfers,
and auto-promotes the lowest-latency active mirror.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple
import httpx

from .registry import DomainRegistry, get_registry
from .dns_tracker import DoHTracker

logger = logging.getLogger("ripper.hoster_watchdog.scanner")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class HosterScanner:
    """Probes all mirrors within each provider group and ranks their health."""

    def __init__(self, registry: Optional[DomainRegistry] = None, timeout: float = 4.0):
        self.registry = registry or get_registry()
        self.timeout = timeout
        self.dns_tracker = DoHTracker(timeout=timeout)

    async def probe_single_mirror(
        self,
        url: str,
        client: httpx.AsyncClient,
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Pings a mirror URL.
        Returns: (is_online, latency_ms, final_redirect_url_if_any)
        """
        start_t = time.perf_counter()
        try:
            resp = await client.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
                follow_redirects=True,
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            # Consider 200, 301, 302, 307, 308, 403 (Cloudflare challenge active means server is up) as online
            if resp.status_code < 500:
                final_url = str(resp.url)
                return True, elapsed_ms, final_url
            return False, elapsed_ms, None
        except Exception:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            return False, elapsed_ms, None

    async def scan_provider(
        self,
        provider_key: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        """
        Evaluates all mirrors for a specific provider.
        Promotes the fastest responding mirror as active.
        """
        if provider_key not in self.registry.providers:
            return None

        provider = self.registry.providers[provider_key]
        should_close = False
        if client is None:
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            client = httpx.AsyncClient(timeout=self.timeout, verify=False, limits=limits)
            should_close = True

        try:
            tasks = [self.probe_single_mirror(m, client) for m in provider.mirrors]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            online_mirrors: List[Tuple[str, float]] = []

            for mirror, res in zip(provider.mirrors, results):
                if isinstance(res, tuple):
                    is_online, latency, redirected_url = res
                    if is_online:
                        target = mirror
                        # If permanent redirect to a new domain, register the new domain
                        if redirected_url:
                            orig_host = urllib.parse.urlparse(mirror).netloc.lower()
                            new_host = urllib.parse.urlparse(redirected_url).netloc.lower()
                            if new_host and new_host != orig_host:
                                target = f"https://{new_host}"
                        online_mirrors.append((target, latency))

            if online_mirrors:
                # Sort by lowest latency
                online_mirrors.sort(key=lambda x: x[1])
                best_mirror, best_latency = online_mirrors[0]
                self.registry.set_active_mirror(provider_key, best_mirror, latency_ms=best_latency)
                return best_mirror
            else:
                provider.status = "offline"
                self.registry.save()
                logger.warning(f"[HosterScanner] All mirrors offline for provider: {provider_key}")
                return None
        finally:
            if should_close:
                await client.aclose()

    async def scan_all_providers(self) -> Dict[str, Optional[str]]:
        """Scans all registered providers concurrently."""
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=25)
        async with httpx.AsyncClient(timeout=self.timeout, verify=False, limits=limits) as client:
            tasks = {
                k: self.scan_provider(k, client=client)
                for k in self.registry.providers
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            return {
                k: (res if isinstance(res, str) else None)
                for k, res in zip(tasks.keys(), results)
            }
