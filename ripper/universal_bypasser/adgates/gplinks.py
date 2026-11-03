"""
GPLinks High-Speed Token Solver.
Resolves gplinks.co / gplinks.in shortlinks via multi-stage HTTP token emulation.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class GPLinksSolver(BaseAdGateSolver):
    """Bypasses GPLinks multi-stage countdown gates."""

    name: str = "gplinks"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            async with self.get_client(follow_redirects=True) as client:
                # Step 1: Initial GET to establish session & cookies
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                # Extract base domain & path
                parsed = urlparse(str(resp.url))
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                html = resp.text

                # Check if already redirected to final destination
                if "gplinks" not in parsed.netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(resp.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                # Step 2: Parse hidden inputs or JavaScript variables
                soup = BeautifulSoup(html, "html.parser")
                form_data = {}

                # Look for form with action or id containing 'link' or 'go'
                forms = soup.find_all("form")
                target_form = None
                for form in forms:
                    action = form.get("action", "")
                    if "go" in action or "link" in action or form.find("input", {"name": "alias"}):
                        target_form = form
                        break

                if target_form:
                    for inp in target_form.find_all("input"):
                        name = inp.get("name")
                        val = inp.get("value", "")
                        if name:
                            form_data[name] = val

                # Regex fallback for embedded tokens if form was incomplete
                if not form_data.get("alias"):
                    alias_m = re.search(r'["\']alias["\']\s*:\s*["\']([^"\']+)["\']', html) or \
                              re.search(r'name=["\']alias["\']\s+value=["\']([^"\']+)["\']', html)
                    if alias_m:
                        form_data["alias"] = alias_m.group(1)

                if not form_data.get("_wpnonce"):
                    nonce_m = re.search(r'["\']_wpnonce["\']\s*:\s*["\']([^"\']+)["\']', html)
                    if nonce_m:
                        form_data["_wpnonce"] = nonce_m.group(1)

                # Step 3: Target endpoint synthesis
                go_url = f"{base_url}/links/go"
                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": str(resp.url),
                    "Origin": base_url,
                }

                post_resp = await client.post(go_url, data=form_data, headers=headers)
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

                # If JSON endpoint failed, check final link in response text
                link_match = re.search(r'https?://[^\s"\'<>]+', post_resp.text)
                if link_match and "gplinks" not in link_match.group(0):
                    dest = link_match.group(0)
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
            error="GPLinks bypass failed to extract destination URL"
        )
