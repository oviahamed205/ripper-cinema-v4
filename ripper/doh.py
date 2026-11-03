"""
DNS over HTTPS (DoH) Resolver for unshorten-cli.
Bypasses local ISP domain blocks and DNS poisoning by resolving hostnames
directly via encrypted Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH endpoints.
"""

from __future__ import annotations

import asyncio
import time
import urllib.parse
from typing import Dict, Optional, Tuple
import httpx

DOH_CLOUDFLARE = "https://1.1.1.1/dns-query"
DOH_GOOGLE = "https://dns.google/resolve"

# In-memory DNS cache: domain -> (ip, expire_timestamp)
_DNS_CACHE: Dict[str, Tuple[str, float]] = {}
_DOH_ENABLED: bool = True


def set_doh_enabled(enabled: bool) -> None:
    """Enable or disable DNS over HTTPS globally."""
    global _DOH_ENABLED
    _DOH_ENABLED = enabled


def is_doh_enabled() -> bool:
    """Check if DoH is active."""
    return _DOH_ENABLED


async def resolve_domain_doh(domain: str, timeout: float = 3.0) -> Optional[str]:
    """
    Resolve domain name to an IPv4 address using DNS over HTTPS (Cloudflare / Google).
    Returns the resolved IP string, or None if resolution failed.
    """
    if not _DOH_ENABLED:
        return None

    clean_domain = domain.strip().lower()
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]

    # Check cache
    now = time.time()
    if clean_domain in _DNS_CACHE:
        ip, expires = _DNS_CACHE[clean_domain]
        if now < expires:
            return ip

    # 1. Try Cloudflare DoH
    headers = {"Accept": "application/dns-json"}
    params = {"name": clean_domain, "type": "A"}

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(DOH_CLOUDFLARE, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1:  # Type A
                        ip = ans.get("data")
                        ttl = max(int(ans.get("TTL", 300)), 60)
                        _DNS_CACHE[clean_domain] = (ip, now + ttl)
                        return ip
    except Exception:
        pass

    # 2. Fallback to Google DoH
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(DOH_GOOGLE, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("Answer", [])
                for ans in answers:
                    if ans.get("type") == 1:
                        ip = ans.get("data")
                        ttl = max(int(ans.get("TTL", 300)), 60)
                        _DNS_CACHE[clean_domain] = (ip, now + ttl)
                        return ip
    except Exception:
        pass

    return None


async def resolve_url_via_doh(url: str, timeout: float = 3.0) -> Tuple[str, Dict[str, str]]:
    """
    Takes a URL, resolves its hostname via DoH, and returns:
    (rewritten_url_with_ip, headers_with_original_host)
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        if not host or host.replace(".", "").isdigit():
            return url, {}

        ip = await resolve_domain_doh(host, timeout=timeout)
        if ip:
            port_str = f":{parsed.port}" if parsed.port else ""
            new_netloc = f"{ip}{port_str}"
            rewritten = parsed._replace(netloc=new_netloc).geturl()
            headers = {"Host": host}
            return rewritten, headers
    except Exception:
        pass

    return url, {}
