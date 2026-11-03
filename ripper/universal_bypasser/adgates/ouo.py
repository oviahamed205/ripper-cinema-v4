"""
Ouo.io / Ouo.press Multi-Step Form Solver.
Solves ouo.io and ouo.press redirection challenges via form token emulation.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class OuoSolver(BaseAdGateSolver):
    """Bypasses Ouo.io and Ouo.press shorteners."""

    name: str = "ouo"

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            # Replace ouo.press with ouo.io if needed
            clean_url = url.replace("ouo.press", "ouo.io")
            async with self.get_client(follow_redirects=True) as client:
                # Step 1: Initial Page
                resp = await client.get(clean_url)
                intermediates.append(str(resp.url))

                parsed = urlparse(str(resp.url))
                if "ouo" not in parsed.netloc:
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

                # Extract token
                def extract_form_data(html_text: str):
                    soup = BeautifulSoup(html_text, "html.parser")
                    form = soup.find("form")
                    data = {}
                    action = ""
                    if form:
                        action = form.get("action", "")
                        for inp in form.find_all("input"):
                            name = inp.get("name")
                            if name:
                                data[name] = inp.get("value", "")
                    return action, data

                action, form_data = extract_form_data(resp.text)
                if not action:
                    # Look for /go/ link
                    m = re.search(r'action=["\'](/go/[^"\']+)["\']', resp.text)
                    if m:
                        action = m.group(1)

                token_m = re.search(r'name=["\']_token["\']\s+value=["\']([^"\']+)["\']', resp.text)
                if token_m and "_token" not in form_data:
                    form_data["_token"] = token_m.group(1)

                target_step1 = urljoin(base_url, action or f"/go/{clean_url.split('/')[-1]}")
                post_resp1 = await client.post(
                    target_step1,
                    data=form_data,
                    headers={"Referer": str(resp.url), "Origin": base_url}
                )
                intermediates.append(str(post_resp1.url))

                parsed1 = urlparse(str(post_resp1.url))
                if "ouo" not in parsed1.netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(post_resp1.url),
                        gate_type=GateType.AD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        intermediate_urls=intermediates
                    )

                # Step 2: Second form submission if needed (ouo has 2 passes)
                action2, form_data2 = extract_form_data(post_resp1.text)
                if not action2:
                    m2 = re.search(r'action=["\'](/xreallcygo/[^"\']+)["\']', post_resp1.text)
                    if m2:
                        action2 = m2.group(1)

                target_step2 = urljoin(base_url, action2 or f"/xreallcygo/{clean_url.split('/')[-1]}")
                post_resp2 = await client.post(
                    target_step2,
                    data=form_data2,
                    headers={"Referer": str(post_resp1.url), "Origin": base_url}
                )
                intermediates.append(str(post_resp2.url))

                parsed2 = urlparse(str(post_resp2.url))
                if "ouo" not in parsed2.netloc:
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=str(post_resp2.url),
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
            error="Ouo.io solver completed 2 steps without redirecting to destination"
        )
