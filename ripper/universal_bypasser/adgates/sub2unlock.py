"""
Social Locker & Sub2Unlock Solver.
Extracts target destination URLs from sub2unlock.com, sub4unlock.com,
social-unlock.com, rekonise.com, and boost.ink without completing social media actions.
"""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class Sub2UnlockSolver(BaseAdGateSolver):
    """Bypasses Sub2Unlock, Social-Unlock, Rekonise, and Boost.ink gates."""

    name: str = "sub2unlock"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()

            async with self.get_client(follow_redirects=True) as client:
                # 1. Specialized API handler for Rekonise
                if "rekonise.com" in netloc:
                    slug = parsed.path.strip("/").split("/")[-1]
                    api_url = f"https://api.rekonise.com/social-unlocks/{slug}"
                    try:
                        api_resp = await client.get(api_url)
                        if api_resp.status_code == 200:
                            data = api_resp.json()
                            target = data.get("url") or data.get("destination")
                            if target and target.startswith(("http://", "https://")):
                                intermediates.append(target)
                                return ShortlinkResult(
                                    original_url=url,
                                    resolved_url=target,
                                    gate_type=GateType.AD_GATE,
                                    success=True,
                                    duration=time.time() - start_time,
                                    solver_used="rekonise_api",
                                    intermediate_urls=intermediates
                                )
                    except Exception:
                        pass

                # 2. Page fetch for DOM/Script extraction (Sub2Unlock, Sub4Unlock, Social-Unlock, Boost.ink)
                resp = await client.get(url)
                intermediates.append(str(resp.url))
                html = resp.text

                # Check if redirected directly
                if parsed.netloc not in urlparse(str(resp.url)).netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                soup = BeautifulSoup(html, "html.parser")

                # Strategy A: Check data attributes on target/unlock buttons
                for el in soup.find_all(attrs={"data-url": True}):
                    candidate = el["data-url"]
                    if candidate.startswith(("http://", "https://")) and netloc not in candidate:
                        intermediates.append(candidate)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=candidate,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="sub2unlock_data_attr",
                            intermediate_urls=intermediates
                        )

                for el in soup.find_all(attrs={"data-target": True}):
                    candidate = el["data-target"]
                    if candidate.startswith(("http://", "https://")) and netloc not in candidate:
                        intermediates.append(candidate)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=candidate,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="sub2unlock_data_attr",
                            intermediate_urls=intermediates
                        )

                # Strategy B: Script variable regex extraction
                patterns = [
                    r'var\s+(?:target_url|targetUrl|destination|unlockUrl|link)\s*=\s*["\'](https?://[^"\']+)["\']',
                    r'["\']destination["\']\s*:\s*["\'](https?://[^"\']+)["\']',
                    r'["\']target["\']\s*:\s*["\'](https?://[^"\']+)["\']',
                    r'window\.location\.href\s*=\s*["\'](https?://[^"\']+)["\']',
                    r'href=["\'](https?://[^"\']+)["\']\s+id=["\'](?:link-target|get-link|btn-main)["\']',
                ]

                for pat in patterns:
                    m = re.search(pat, html)
                    if m:
                        candidate = m.group(1)
                        if netloc not in candidate and not candidate.endswith((".js", ".css", ".png")):
                            intermediates.append(candidate)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=candidate,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="sub2unlock_script_var",
                                intermediate_urls=intermediates
                            )

                # Strategy C: Base64 decode embedded script payloads
                b64_matches = re.findall(r'atob\(["\']([A-Za-z0-9+/=]{20,})["\']\)', html)
                for b64_str in b64_matches:
                    try:
                        decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
                        if decoded.startswith(("http://", "https://")) and netloc not in decoded:
                            intermediates.append(decoded)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=decoded,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="sub2unlock_b64_script",
                                intermediate_urls=intermediates
                            )
                    except Exception:
                        pass

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
            error="Sub2Unlock solver could not find destination in DOM or API"
        )
