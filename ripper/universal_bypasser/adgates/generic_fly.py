"""
Generic AdLinkFly / ShrinkMe / Vurl Solver.
Universal handler for services built on the AdLinkFly and MightyScripts codebase.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class GenericFlySolver(BaseAdGateSolver):
    """Bypasses AdLinkFly, ShrinkMe, and compatible script-based shorteners."""

    name: str = "generic_fly"

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

                # Check if already reached destination
                if parsed.netloc not in urlparse(url).netloc:
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

                for inp in soup.find_all("input"):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")

                # Common tokens in AdLinkFly
                for pattern in [
                    r'["\']alias["\']\s*:\s*["\']([^"\']+)["\']',
                    r'["\']_wpnonce["\']\s*:\s*["\']([^"\']+)["\']',
                    r'name=["\']csrfToken["\']\s+value=["\']([^"\']+)["\']',
                    r'var\s+app_url\s*=\s*["\']([^"\']+)["\']'
                ]:
                    m = re.search(pattern, html)
                    if m:
                        key = "alias" if "alias" in pattern else ("_wpnonce" if "wpnonce" in pattern else "csrfToken")
                        if key not in form_data:
                            form_data[key] = m.group(1)

                endpoints = ["/links/go", "/links/linkdrop4", "/fly/go", "/go"]
                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": str(resp.url),
                    "Origin": base_url,
                }

                for ep in endpoints:
                    try:
                        target_ep = urljoin(base_url, ep)
                        post_resp = await client.post(target_ep, data=form_data, headers=headers)
                        if post_resp.status_code == 200:
                            try:
                                js = post_resp.json()
                                if js.get("url"):
                                    dest = js["url"]
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

                            urls = re.findall(r'https?://[^\s"\'<>]+', post_resp.text)
                            for u in urls:
                                if parsed.netloc not in urlparse(u).netloc and not u.endswith((".js", ".css", ".png")):
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
                    except Exception:
                        continue

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
            error="Generic AdLinkFly solver could not extract target destination"
        )
