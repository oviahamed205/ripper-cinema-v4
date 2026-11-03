"""
Cloud Bypass Bridge.
Interfaces with public bypass REST services (bypass.city, adbypass.org)
for resolving complex Turnstile / Cloudflare-protected shortlinks (Linkvertise, Lootlabs).
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import quote

import httpx

from ripper.universal_bypasser.models import BypassContext, GateType, ShortlinkResult


class CloudBypassBridge:
    """REST client for external cloud bypass APIs."""

    def __init__(self, context: Optional[BypassContext] = None):
        self.context = context or BypassContext()

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        # Try bypass.city REST API
        try:
            encoded_url = quote(url, safe="")
            api_endpoint = f"https://bypass.city/api/bypass?url={encoded_url}"

            headers = {
                "User-Agent": self.context.user_agent,
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(headers=headers, timeout=self.context.timeout, verify=False) as client:
                resp = await client.get(api_endpoint)
                if resp.status_code == 200:
                    data = resp.json()
                    # bypass.city returns {"destination": "..."} or {"target": "..."}
                    dest = data.get("destination") or data.get("target") or data.get("url")
                    if dest and dest.startswith(("http://", "https://")):
                        intermediates.append(dest)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=dest,
                            gate_type=GateType.CLOUD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="cloud_bypass_city",
                            intermediate_urls=intermediates
                        )
        except Exception:
            pass

        # Try adbypass.org REST API
        try:
            encoded_url = quote(url, safe="")
            api_endpoint2 = f"https://adbypass.org/api/bypass?url={encoded_url}"

            headers = {
                "User-Agent": self.context.user_agent,
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(headers=headers, timeout=self.context.timeout, verify=False) as client:
                resp = await client.get(api_endpoint2)
                if resp.status_code == 200:
                    data = resp.json()
                    dest = data.get("destination") or data.get("result") or data.get("url")
                    if dest and dest.startswith(("http://", "https://")):
                        intermediates.append(dest)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=dest,
                            gate_type=GateType.CLOUD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="cloud_adbypass_org",
                            intermediate_urls=intermediates
                        )
        except Exception:
            pass

        return ShortlinkResult(
            original_url=url,
            resolved_url=None,
            gate_type=GateType.CLOUD_GATE,
            success=False,
            duration=time.time() - start_time,
            solver_used="cloud_bypass_bridge",
            intermediate_urls=intermediates,
            error="Cloud bypass bridges failed to resolve URL"
        )
