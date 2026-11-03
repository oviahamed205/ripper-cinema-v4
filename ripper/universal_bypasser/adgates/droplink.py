"""
Droplink / Dropeps High-Speed Token Solver.
Resolves droplink.co / dropeps.com shortlinks via session extraction and form payload synthesis.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class DroplinkSolver(BaseAdGateSolver):
    """Bypasses Droplink and Dropeps countdown gates."""

    name: str = "droplink"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                if "droplink" not in parsed.netloc and "dropeps" not in parsed.netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                base_url = f"{parsed.scheme}://{parsed.netloc}"
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                # Extract form data
                form = soup.find("form", id=re.compile(r"link|go|main", re.I)) or soup.find("form")
                post_data = {}
                action = "/links/go"

                if form:
                    if form.get("action"):
                        action = form.get("action")
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        if name:
                            post_data[name] = inp.get("value", "")

                # Extra token parsing via regex
                tokens = re.findall(r'name=["\']([^"\']+)["\']\s+value=["\']([^"\']+)["\']', html)
                for name, val in tokens:
                    if name not in post_data:
                        post_data[name] = val

                target_post_url = urljoin(base_url, action)
                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": str(resp.url),
                    "Origin": base_url,
                }

                post_resp = await client.post(target_post_url, data=post_data, headers=headers)
                intermediates.append(str(post_resp.url))

                if post_resp.status_code == 200:
                    try:
                        res_json = post_resp.json()
                        if "url" in res_json and res_json["url"]:
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

                # Direct URL pattern in response text
                urls = re.findall(r'https?://[^\s"\'<>]+', post_resp.text)
                for u in urls:
                    u_netloc = urlparse(u).netloc
                    if "droplink" not in u_netloc and "dropeps" not in u_netloc and not u.endswith((".js", ".css", ".png", ".jpg")):
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
            error="Droplink resolution did not yield final target URL"
        )
