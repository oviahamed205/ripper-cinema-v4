"""
ripper.hoster_watchdog.dns_tracker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DNS-over-HTTPS (DoH) change and rotation tracker.
Queries Cloudflare (1.1.1.1) and Google (8.8.8.8) DoH APIs to detect
A-record, CNAME, and redirection changes for hoster domains.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger("ripper.hoster_watchdog.dns_tracker")

CLOUDFLARE_DOH = "https://cloudflare-dns.com/dns-query"
GOOGLE_DOH = "https://dns.google/resolve"


class DoHTracker:
    """Probes domain DNS status and detects CNAME aliases or domain shifts."""

    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout

    async def resolve_domain(
        self,
        domain: str,
        record_type: str = "A",
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[str]:
        """Queries DoH for IP addresses or CNAME targets."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, verify=False)
            should_close = True

        answers: List[str] = []
        try:
            # Query Cloudflare DoH (Accept: application/dns-json)
            params = {"name": domain, "type": record_type}
            headers = {"Accept": "application/dns-json"}
            resp = await client.get(CLOUDFLARE_DOH, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for ans in data.get("Answer", []):
                    ans_data = ans.get("data")
                    if ans_data:
                        answers.append(ans_data.rstrip("."))
        except Exception as e:
            logger.debug(f"[DoH] Cloudflare DoH query failed for {domain}: {e}")

        # Fallback to Google DoH if Cloudflare had no answer
        if not answers:
            try:
                params = {"name": domain, "type": record_type}
                resp = await client.get(GOOGLE_DOH, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for ans in data.get("Answer", []):
                        ans_data = ans.get("data")
                        if ans_data:
                            answers.append(ans_data.rstrip("."))
            except Exception as e:
                logger.debug(f"[DoH] Google DoH query failed for {domain}: {e}")

        if should_close:
            await client.aclose()

        return answers

    async def check_canonical_shift(self, domain: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
        """Checks if a domain has set a CNAME alias pointing to a new mirror."""
        cnames = await self.resolve_domain(domain, record_type="CNAME", client=client)
        if cnames:
            return cnames[0]
        return None
