"""
Try2Link Specialized Ad-Gate Solver.
Handles Try2link.com / Try2link.net shorteners via header spoofing,
parameter generation (d-timestamp offset), and AJAX endpoint traversal.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class Try2LinkSolver(BaseAdGateSolver):
    """Solves Try2Link ad gates via automated token exchange and simulated countdown."""

    name: str = "try2link"

    SUPPORTED_DOMAINS = {
        "try2link.com",
        "try2link.net",
        "try2link.org",
        "try2link.link",
    }

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://newforex.online/",
                "Accept-Language": "en-US,en;q=0.9",
            }

            async with self.get_client(headers=headers, follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                # Check if already reached final URL
                cur_domain = urlparse(str(resp.url)).netloc.lower()
                if not any(d in cur_domain for d in self.SUPPORTED_DOMAINS):
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="try2link_direct",
                        intermediate_urls=intermediates,
                    )

                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                # Look for form with action or id /links/go
                form = soup.find("form", action=re.compile(r"/links/go", re.I)) or soup.find("form")
                post_url = urljoin(str(resp.url), "/links/go")
                post_data = {}

                if form:
                    if form.get("action"):
                        post_url = urljoin(str(resp.url), form["action"])
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        val = inp.get("value", "")
                        if name:
                            post_data[name] = val

                # Ensure timestamp delta is added
                if "d" not in post_data:
                    post_data["d"] = str(int(time.time()) + 240)

                # Send AJAX request with requested-with
                ajax_headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": str(resp.url),
                    "Origin": f"{urlparse(str(resp.url)).scheme}://{urlparse(str(resp.url)).netloc}",
                }

                post_resp = await client.post(post_url, data=post_data, headers=ajax_headers)
                intermediates.append(str(post_resp.url))

                try:
                    data = post_resp.json()
                    if isinstance(data, dict):
                        target = data.get("url") or data.get("link") or data.get("href")
                        if target:
                            intermediates.append(target)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=target,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="try2link_ajax",
                                intermediate_urls=intermediates,
                            )
                except Exception:
                    pass

                # Fallback: check post response text for redirect url
                m = re.search(r'["\']url["\']\s*:\s*["\'](https?://[^"\']+)["\']', post_resp.text)
                if m:
                    target = m.group(1).replace(r"\/", "/")
                    intermediates.append(target)
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=target,
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="try2link_regex",
                        intermediate_urls=intermediates,
                    )

                # Check if final redirect was followed
                if str(post_resp.url) != url and not any(d in urlparse(str(post_resp.url)).netloc for d in self.SUPPORTED_DOMAINS):
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(post_resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="try2link_redirect",
                        intermediate_urls=intermediates,
                    )

        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=url,
                gate_type=GateType.AD_GATE,
                success=False,
                error=f"Try2Link solver error: {str(e)}",
                duration=time.time() - start_time,
                solver_used=self.name,
                intermediate_urls=intermediates,
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=url,
            gate_type=GateType.AD_GATE,
            success=False,
            error="Could not bypass Try2Link gate",
            duration=time.time() - start_time,
            solver_used=self.name,
            intermediate_urls=intermediates,
        )
