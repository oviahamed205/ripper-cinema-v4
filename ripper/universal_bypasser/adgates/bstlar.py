"""
Bstlar (Boostellar) Dedicated Social Unlocker & Gate Solver.
Handles bstlar.com and direct sub-link tokens by inspecting Next.js hydration props,
hidden DOM target attributes, and unlocking REST endpoints.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class BstlarSolver(BaseAdGateSolver):
    """Solves Bstlar.com and affiliated boostellar links."""

    name: str = "bstlar"

    SUPPORTED_DOMAINS = {
        "bstlar.com",
        "bst.gg",
        "bstlar.io",
    }

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

            async with self.get_client(headers=headers, follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                # Check if already redirected away from bstlar
                cur_domain = urlparse(str(resp.url)).netloc.lower()
                if not any(d in cur_domain for d in self.SUPPORTED_DOMAINS):
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="bstlar_direct",
                        intermediate_urls=intermediates,
                    )

                html = resp.text

                # 1. Check Next.js __NEXT_DATA__ JSON props
                m_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                if m_next:
                    try:
                        next_json = json.loads(m_next.group(1))
                        props = next_json.get("props", {}).get("pageProps", {})
                        # Search for target URL in link data
                        link_obj = props.get("link") or props.get("linkData") or props
                        if isinstance(link_obj, dict):
                            target = (
                                link_obj.get("target_url")
                                or link_obj.get("url")
                                or link_obj.get("destination")
                                or link_obj.get("link")
                            )
                            if target and target.startswith(("http://", "https://")):
                                intermediates.append(target)
                                return ShortlinkResult(
                                    original_url=url,
                                    resolved_url=target,
                                    gate_type=GateType.AD_GATE,
                                    success=True,
                                    duration=time.time() - start_time,
                                    solver_used="bstlar_nextjs_props",
                                    intermediate_urls=intermediates,
                                )
                    except Exception:
                        pass

                # 2. Check inline JSON objects or variables
                m_var = re.search(r'["\'](?:target_url|destination|unlocked_url)["\']\s*:\s*["\'](https?://[^"\']+)["\']', html)
                if m_var:
                    target = m_var.group(1).replace(r"\/", "/")
                    intermediates.append(target)
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=target,
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="bstlar_inline_var",
                        intermediate_urls=intermediates,
                    )

                # 3. Check for link slug and call internal unlock API
                slug_match = re.search(r'bstlar\.com/(?:[a-zA-Z0-9_\-]+/)?([a-zA-Z0-9_\-]+)', url)
                if slug_match:
                    slug = slug_match.group(1)
                    api_endpoints = [
                        f"https://bstlar.com/api/link?url={slug}",
                        f"https://bstlar.com/api/links/{slug}",
                        f"https://bstlar.com/api/unlock/{slug}",
                    ]
                    api_headers = {
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": str(resp.url),
                    }
                    for api_url in api_endpoints:
                        try:
                            api_resp = await client.get(api_url, headers=api_headers)
                            if api_resp.status_code == 200:
                                api_data = api_resp.json()
                                if isinstance(api_data, dict):
                                    target = (
                                        api_data.get("target_url")
                                        or api_data.get("url")
                                        or api_data.get("destination")
                                    )
                                    if target and target.startswith(("http://", "https://")):
                                        intermediates.append(target)
                                        return ShortlinkResult(
                                            original_url=url,
                                            resolved_url=target,
                                            gate_type=GateType.AD_GATE,
                                            success=True,
                                            duration=time.time() - start_time,
                                            solver_used="bstlar_api",
                                            intermediate_urls=intermediates,
                                        )
                        except Exception:
                            continue

        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=url,
                gate_type=GateType.AD_GATE,
                success=False,
                error=f"Bstlar solver error: {str(e)}",
                duration=time.time() - start_time,
                solver_used=self.name,
                intermediate_urls=intermediates,
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=url,
            gate_type=GateType.AD_GATE,
            success=False,
            error="Could not extract target destination from Bstlar page",
            duration=time.time() - start_time,
            solver_used=self.name,
            intermediate_urls=intermediates,
        )
