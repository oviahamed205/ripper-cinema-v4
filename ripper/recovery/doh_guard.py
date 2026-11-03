"""
Network Immunity & DNS-over-HTTPS Guard (Commandment 6).
Transparently resolves domains via encrypted Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH.
"""

from __future__ import annotations

from typing import Optional
from ..doh import resolve_domain_doh, is_doh_enabled
from .telemetry import log_event


async def resolve_with_doh_fallback(hostname: str) -> Optional[str]:
    """
    Attempts DNS resolution via encrypted DoH if standard system DNS fails or is blocked.
    """
    if not is_doh_enabled():
        return None

    ip = await resolve_domain_doh(hostname)
    if ip:
        log_event("DNS_BYPASS", f"Successfully bypassed ISP block for '{hostname}' -> {ip}")
    return ip
