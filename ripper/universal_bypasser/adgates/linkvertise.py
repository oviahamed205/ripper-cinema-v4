"""
Linkvertise Dedicated Solver & Bridge.
Resolves linkvertise.com, link-to.net, up-to-down.net, direct-link.net, and file-link.net
via embedded parameter extraction, internal redirect API, and fallback cloud bridge.
"""

from __future__ import annotations

import base64
import re
import time
from urllib.parse import parse_qs, urlparse

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.bridges.cloud_bridge import CloudBypassBridge
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class LinkvertiseSolver(BaseAdGateSolver):
    """Bypasses Linkvertise and associated multi-tier interstitial domains."""

    name: str = "linkvertise"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        # 1. Fast path: Check for embedded ?r= base64 redirect parameter
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if "r" in query and query["r"]:
            raw_r = query["r"][0]
            try:
                rem = len(raw_r) % 4
                if rem:
                    raw_r += "=" * (4 - rem)
                decoded = base64.b64decode(raw_r).decode("utf-8", errors="ignore")
                if decoded.startswith(("http://", "https://")):
                    intermediates.append(decoded)
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=decoded,
                        gate_type=GateType.CLOUD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="linkvertise_b64_param",
                        intermediate_urls=intermediates
                    )
            except Exception:
                pass

        # 2. Linkvertise Static API Endpoint Query
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) >= 2:
            user_id = path_parts[0]
            slug = path_parts[1]
            api_endpoint = f"https://publisher.linkvertise.com/api/v1/redirect/link/static/{user_id}/{slug}"

            try:
                headers = {
                    "User-Agent": self.context.user_agent,
                    "Accept": "application/json",
                }
                async with self.get_client(follow_redirects=True) as client:
                    api_resp = await client.get(api_endpoint, headers=headers)
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        link_data = data.get("data", {}).get("link", {})
                        target = link_data.get("url") or link_data.get("target_host")
                        if target and target.startswith(("http://", "https://")):
                            intermediates.append(target)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=target,
                                gate_type=GateType.CLOUD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="linkvertise_api",
                                intermediate_urls=intermediates
                            )
            except Exception:
                pass

        # 3. Fallback to Cloud Bypass Bridge (bypass.city / adbypass.org)
        if self.context.use_cloud_bridge:
            bridge = CloudBypassBridge(self.context)
            bridge_res = await bridge.solve(url)
            if bridge_res.success and bridge_res.resolved_url:
                intermediates.extend(bridge_res.intermediate_urls)
                return ShortlinkResult(
                    original_url=url,
                    resolved_url=bridge_res.resolved_url,
                    gate_type=GateType.CLOUD_GATE,
                    success=True,
                    duration=time.time() - start_time,
                    solver_used=f"linkvertise_{bridge_res.solver_used}",
                    intermediate_urls=intermediates
                )

        return ShortlinkResult(
            original_url=url,
            resolved_url=None,
            gate_type=GateType.CLOUD_GATE,
            success=False,
            duration=time.time() - start_time,
            solver_used=self.name,
            intermediate_urls=intermediates,
            error="Linkvertise solver could not extract target URL via local API or cloud bridge"
        )
