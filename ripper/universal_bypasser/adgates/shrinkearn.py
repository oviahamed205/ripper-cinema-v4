"""
ShrinkEarn / Earn4Link Dedicated Solver.
Resolves shrinkearn.com, shrinkforearn.in, and earn4link.com shortlink challenges.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class ShrinkEarnSolver(BaseAdGateSolver):
    """Bypasses ShrinkEarn, ShrinkForEarn, and Earn4Link multi-stage gates."""

    name: str = "shrinkearn"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                html = resp.text

                # Check if already redirected
                if "shrinkearn" not in parsed.netloc and "shrinkforearn" not in parsed.netloc and "earn4link" not in parsed.netloc:
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
                form_data = {}

                target_form = soup.find("form", id=re.compile(r"link|go|main", re.I)) or soup.find("form")
                if target_form:
                    for inp in target_form.find_all("input"):
                        name = inp.get("name")
                        if name:
                            form_data[name] = inp.get("value", "")

                # Additional token patterns
                for key, pat in [
                    ("alias", r'["\']alias["\']\s*:\s*["\']([^"\']+)["\']'),
                    ("_wpnonce", r'["\']_wpnonce["\']\s*:\s*["\']([^"\']+)["\']'),
                    ("csrfToken", r'name=["\']csrfToken["\']\s+value=["\']([^"\']+)["\']'),
                ]:
                    if key not in form_data:
                        m = re.search(pat, html)
                        if m:
                            form_data[key] = m.group(1)

                target_endpoint = urljoin(base_url, "/links/go")
                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": str(resp.url),
                    "Origin": base_url,
                }

                post_resp = await client.post(target_endpoint, data=form_data, headers=headers)
                intermediates.append(str(post_resp.url))

                if post_resp.status_code == 200:
                    try:
                        res_json = post_resp.json()
                        if res_json.get("status") == "success" and res_json.get("url"):
                            dest = res_json["url"]
                            intermediates.append(dest)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=dest,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used=self.name,
                                intermediate_urls=intermediates
                            )
                    except Exception:
                        pass

                # Scan for outbound links
                urls = re.findall(r'https?://[^\s"\'<>]+', post_resp.text)
                for u in urls:
                    u_netloc = urlparse(u).netloc
                    if not any(se in u_netloc for se in ["shrinkearn", "shrinkforearn", "earn4link"]) and not u.endswith((".js", ".css", ".png")):
                        intermediates.append(u)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=u,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used=self.name,
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
            error="ShrinkEarn solver could not extract final destination URL"
        )
