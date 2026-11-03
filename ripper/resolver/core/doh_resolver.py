"""
DNS-over-HTTPS (DoH) Anti-Censorship & Failover Engine for Ripper Resolver.
Transparently catches socket.gaierror / DNS poisoning and resolves hostnames via
Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH with in-memory TTL caching.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# In-memory DoH cache: host -> (ip, expire_time)
_DOH_CACHE: Dict[str, Tuple[str, float]] = {}
_DOH_LOCK = asyncio.Lock()

CLOUDFLARE_DOH_ENDPOINT = "https://1.1.1.1/dns-query"
GOOGLE_DOH_ENDPOINT = "https://dns.google/resolve"


async def resolve_doh(host: str, timeout: float = 4.0) -> Optional[str]:
    """
    Resolve a hostname to an IPv4 address using DNS-over-HTTPS.
    Queries Cloudflare DoH first, falling back to Google DoH.
    """
    clean_host = (host or "").strip().lower()
    if not clean_host:
        return None

    # Check cache first
    now = time.monotonic()
    cached = _DOH_CACHE.get(clean_host)
    if cached and cached[1] > now:
        return cached[0]

    async with _DOH_LOCK:
        # Re-check after lock acquisition
        cached = _DOH_CACHE.get(clean_host)
        if cached and cached[1] > time.monotonic():
            return cached[0]

        ip: Optional[str] = None
        ttl: int = 300

        # Try Cloudflare DoH
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.get(
                    CLOUDFLARE_DOH_ENDPOINT,
                    params={"name": clean_host, "type": "A"},
                    headers={"Accept": "application/dns-json"},
                )
                if res.status_code == 200:
                    data = res.json()
                    answers = data.get("Answer", [])
                    for ans in answers:
                        if ans.get("type") == 1 and ans.get("data"):
                            ip = ans["data"].strip()
                            ttl = max(60, int(ans.get("TTL", 300)))
                            break
        except Exception as exc:
            logger.debug("Cloudflare DoH failed for %s: %s", clean_host, exc)

        # Fallback to Google DoH if Cloudflare didn't return an A record
        if not ip:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    res = await client.get(
                        GOOGLE_DOH_ENDPOINT,
                        params={"name": clean_host, "type": "A"},
                        headers={"Accept": "application/dns-json"},
                    )
                    if res.status_code == 200:
                        data = res.json()
                        answers = data.get("Answer", [])
                        for ans in answers:
                            if ans.get("type") == 1 and ans.get("data"):
                                ip = ans["data"].strip()
                                ttl = max(60, int(ans.get("TTL", 300)))
                                break
            except Exception as exc:
                logger.debug("Google DoH failed for %s: %s", clean_host, exc)

        if ip:
            _DOH_CACHE[clean_host] = (ip, time.monotonic() + ttl)
            logger.info("DoH resolved %s -> %s (TTL=%ds)", clean_host, ip, ttl)
            return ip

    return None


def clear_doh_cache() -> None:
    """Clear in-memory DoH cache."""
    _DOH_CACHE.clear()
