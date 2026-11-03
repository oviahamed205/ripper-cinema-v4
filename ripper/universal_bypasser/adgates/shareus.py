"""
Shareus / Shrs.link High-Speed Token Solver.
Resolves shareus.io and shrs.link shorteners via API token parsing and JSON payload extraction.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class ShareusSolver(BaseAdGateSolver):
    """Bypasses Shareus.io and Shrs.link token gates."""

    name: str = "shareus"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                if "shareus" not in parsed.netloc and "shrs.link" not in parsed.netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                html = resp.text
                base_url = f"{parsed.scheme}://{parsed.netloc}"

                # Extract sid from query or html
                query_params = parse_qs(parsed.query)
                sid = query_params.get("sid", [None])[0]
                if not sid:
                    sid_m = re.search(r'["\']sid["\']\s*:\s*["\']([^"\']+)["\']', html) or \
                            re.search(r'sid=([a-zA-Z0-9_-]+)', html)
                    if sid_m:
                        sid = sid_m.group(1)

                # Strategy 1: Shareus internal API query
                if sid:
                    api_endpoints = [
                        f"{base_url}/api?shortid={sid}",
                        f"{base_url}/go?sid={sid}",
                        f"https://shareus.io/api?shortid={sid}",
                    ]
                    headers = {
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": str(resp.url),
                        "Accept": "application/json, text/plain, */*",
                    }
                    for ep in api_endpoints:
                        try:
                            api_resp = await client.get(ep, headers=headers)
                            if api_resp.status_code == 200:
                                try:
                                    data = api_resp.json()
                                    target = data.get("link") or data.get("target") or data.get("url")
                                    if target and target.startswith(("http://", "https://")):
                                        intermediates.append(target)
                                        return ShortlinkResult(
                                            original_url=url,
                                            resolved_url=target,
                                            gate_type=GateType.AD_GATE,
                                            success=True,
                                            duration=time.time() - start_time,
                                            solver_used="shareus_api",
                                            intermediate_urls=intermediates
                                        )
                                except Exception:
                                    pass
                        except Exception:
                            continue

                # Strategy 2: Extract destination URL directly from DOM / scripts
                urls = re.findall(r'https?://[^\s"\'<>]+', html)
                for u in urls:
                    u_domain = urlparse(u).netloc.lower()
                    if "shareus" not in u_domain and "shrs.link" not in u_domain and not u.endswith((".js", ".css", ".png")):
                        if any(host in u_domain for host in ["drive.google", "mega.nz", "streamtape", "dood", "mixdrop"]):
                            intermediates.append(u)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=u,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="shareus_dom_scan",
                                intermediate_urls=intermediates
                            )

        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=None,
                gate_type=GateType.AD_GATE,
                success=False,
                duration=time.time() - start_time,
                solver_used=self.name,
                intermediate_urls=intermediates,
                error=str(e)
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=None,
            gate_type=GateType.AD_GATE,
            success=False,
            duration=time.time() - start_time,
            solver_used=self.name,
            intermediate_urls=intermediates,
            error="Shareus solver could not extract target destination"
        )
