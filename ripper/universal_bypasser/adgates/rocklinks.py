"""
Rocklinks Solver.
Handles rocklinks.net / rocklinks.top AdLinkFly derivatives.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class RocklinksSolver(BaseAdGateSolver):
    """Bypasses Rocklinks ad-shortener gates."""

    name: str = "rocklinks"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                if "rocklinks" not in parsed.netloc:
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

                form_data = {}
                for inp in soup.find_all("input"):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")

                # Look for alias and nonce in script tags if missing
                if not form_data.get("alias"):
                    m_alias = re.search(r'["\']?alias["\']?\s*[:=]\s*["\']([^"\']+)["\']', html)
                    if m_alias:
                        form_data["alias"] = m_alias.group(1)

                if not form_data.get("_wpnonce"):
                    m_nonce = re.search(r'["\']?_wpnonce["\']?\s*[:=]\s*["\']([^"\']+)["\']', html)
                    if m_nonce:
                        form_data["_wpnonce"] = m_nonce.group(1)

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
                    if "rocklinks" not in urlparse(u).netloc and not u.endswith((".js", ".css", ".png", ".jpg")):
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
            error="Rocklinks solver could not resolve destination URL"
        )
