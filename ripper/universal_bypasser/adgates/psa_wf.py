"""
PSA.wf & Associated Multi-Domain Ad-Gate Solver.
Incorporates specialized bypass routines for psa.wf, go2.pics, cashgrowth.online,
ravellawfirm.com, themezon.net, fc.lc, and tpi.li / oii.la.
"""

from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class PSAWfSolver(BaseAdGateSolver):
    """Solves PSA.wf, Go2.pics, CashGrowth, RavelLawFirm, and FC.lc networks."""

    name: str = "psa_wf"

    @staticmethod
    def unwrap_go2_chain(start_url: str, max_depth: int = 8) -> str:
        """Recursively decodes nested go2.pics base64 chain."""
        cur = start_url
        for _ in range(max_depth):
            try:
                parsed = urlparse(cur)
                if "go2.pics" in parsed.netloc:
                    q = parse_qs(parsed.query)
                    raw_id = q.get("id", [None])[0]
                    if raw_id:
                        clean_b64 = raw_id.replace("-", "+").replace("_", "/")
                        rem = len(clean_b64) % 4
                        if rem:
                            clean_b64 += "=" * (4 - rem)
                        decoded = base64.b64decode(clean_b64.encode("ascii")).decode("utf-8", errors="ignore")
                        if decoded.startswith(("http://", "https://")):
                            cur = decoded
                            continue
            except Exception:
                break
            break
        return cur

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        # 1. Immediate go2.pics recursive decode
        if "go2.pics" in url:
            unwrapped = self.unwrap_go2_chain(url)
            if unwrapped != url:
                intermediates.append(unwrapped)
                return ShortlinkResult(
                    original_url=url,
                    resolved_url=unwrapped,
                    gate_type=GateType.AD_GATE,
                    success=True,
                    duration=time.time() - start_time,
                    solver_used="go2_chain_unroll",
                    intermediate_urls=intermediates
                )

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                intermediates.append(str(resp.url))

                html = resp.text
                parsed = urlparse(str(resp.url))
                domain = parsed.netloc.lower()
                base_url = f"{parsed.scheme}://{parsed.netloc}"

                # 2. RavelLawFirm AST island props
                if "ravellawfirm.com" in domain:
                    m = re.search(r'"finalDestination":\s*\[\d+,\s*"([^"]+)"\]', html)
                    if m:
                        dest = m.group(1)
                        if "go2.pics" in dest:
                            dest = self.unwrap_go2_chain(dest)
                        intermediates.append(dest)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=dest,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="ravellawfirm_props",
                            intermediate_urls=intermediates
                        )

                # 3. CashGrowth session API
                if "cashgrowth.online" in domain or "starkroboticsfrc.com" in domain:
                    # Look for session ID in html
                    m_session = re.search(r'["\'](?:sessionId|session_id)["\']\s*:\s*["\']([^"\']+)["\']', html)
                    session_url = f"{base_url}/api/session/"
                    try:
                        api_resp = await client.get(session_url)
                        if api_resp.status_code == 200:
                            data = api_resp.json()
                            dest = data.get("redirect") or data.get("data", {}).get("finalRedirect")
                            if dest and dest.startswith(("http://", "https://")):
                                intermediates.append(dest)
                                return ShortlinkResult(
                                    original_url=url,
                                    resolved_url=dest,
                                    gate_type=GateType.AD_GATE,
                                    success=True,
                                    duration=time.time() - start_time,
                                    solver_used="cashgrowth_api",
                                    intermediate_urls=intermediates
                                )
                    except Exception:
                        pass

                # 4. FC.lc / Jobzhub
                if any(k in domain for k in ["fc-lc", "fc.lc", "jobzhub"]):
                    m = re.search(r'REDIRECT_URL\s*=\s*"([^"]+)"', html)
                    if m:
                        dest = m.group(1)
                        intermediates.append(dest)
                        return ShortlinkResult(
                            original_url=url,
                            resolved_url=dest,
                            gate_type=GateType.AD_GATE,
                            success=True,
                            duration=time.time() - start_time,
                            solver_used="fclc_redirect_var",
                            intermediate_urls=intermediates
                        )

                # 5. Tpi.li / Oii.la Base64 Payload Scanner
                if "tpi.li" in domain or "oii.la" in domain:
                    m = re.search(r'aHR0c[a-zA-Z0-9+/=]+(?<!=)', html)
                    if m:
                        raw_b64 = m.group(0)
                        rem = len(raw_b64) % 4
                        if rem:
                            raw_b64 += "=" * (4 - rem)
                        decoded = base64.b64decode(raw_b64.encode("ascii")).decode("utf-8", errors="ignore")
                        if decoded.startswith(("http://", "https://")) and domain not in decoded:
                            intermediates.append(decoded)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=decoded,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="tpili_b64_scan",
                                intermediate_urls=intermediates
                            )

                # 6. PSA.wf goto form
                if "psa.wf" in domain and "/goto/" in url:
                    soup = BeautifulSoup(html, "html.parser")
                    form = soup.find("form", id=re.compile(r"redirect", re.I)) or soup.find("form")
                    if form:
                        action = form.get("action", "")
                        post_data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
                        target_ep = urljoin(base_url, action)
                        post_resp = await client.post(target_ep, data=post_data, headers={"Referer": str(resp.url)})
                        intermediates.append(str(post_resp.url))
                        if parsed.netloc not in urlparse(str(post_resp.url)).netloc:
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=str(post_resp.url),
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="psawf_form_submit",
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
            error="PSA.wf solver could not locate destination in response"
        )
