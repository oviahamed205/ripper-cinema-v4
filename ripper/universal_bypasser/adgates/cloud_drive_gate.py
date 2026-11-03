"""
Cloud Drive Gate Solver.
Resolves intermediate cloud-drive wrappers and authentication gates
such as katdrive.net, gadrive.com, sharer.pw, drivehub.me, and kolop.net.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.models import GateType, ShortlinkResult


class CloudDriveGateSolver(BaseAdGateSolver):
    """Bypasses intermediate Google Drive and cloud storage landing gates."""

    name: str = "cloud_drive_gate"

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

                # Check if already reached a cloud storage destination
                if any(k in parsed.netloc for k in ["drive.google.com", "mega.nz", "1fichier.com", "pixeldrain.com"]):
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

                # Strategy 1: Check for download buttons with direct external link
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith(("http://", "https://")):
                        h_netloc = urlparse(href).netloc.lower()
                        if any(dest in h_netloc for dest in ["drive.google.com", "mega.nz", "pixeldrain.com", "1fichier.com", "gofile.io", "r2.cloudflarestorage.com"]):
                            intermediates.append(href)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=href,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="cloud_drive_btn_scan",
                                intermediate_urls=intermediates
                            )

                # Strategy 2: Script variable regex for direct stream/download URL
                patterns = [
                    r'var\s+(?:download_url|file_url|stream_url|direct_link)\s*=\s*["\'](https?://[^"\']+)["\']',
                    r'["\'](?:download_url|direct_url)["\']\s*:\s*["\'](https?://[^"\']+)["\']',
                    r'window\.location\s*=\s*["\'](https?://[^"\']+)["\']',
                ]

                for pat in patterns:
                    m = re.search(pat, html)
                    if m:
                        candidate = m.group(1)
                        if parsed.netloc not in urlparse(candidate).netloc:
                            intermediates.append(candidate)
                            return ShortlinkResult(
                                original_url=url,
                                resolved_url=candidate,
                                gate_type=GateType.AD_GATE,
                                success=True,
                                duration=time.time() - start_time,
                                solver_used="cloud_drive_script_var",
                                intermediate_urls=intermediates
                            )

                # Strategy 3: Form submission for /download or /drive endpoints
                forms = soup.find_all("form")
                for form in forms:
                    action = form.get("action", "")
                    post_data = {}
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        if name:
                            post_data[name] = inp.get("value", "")

                    if "download" in action or "drive" in action or post_data.get("token") or post_data.get("code"):
                        target_ep = urljoin(base_url, action)
                        post_resp = await client.post(target_ep, data=post_data, headers={"Referer": str(resp.url)})
                        intermediates.append(str(post_resp.url))

                        if post_resp.status_code in (200, 302):
                            if any(k in str(post_resp.url) for k in ["drive.google.com", "mega.nz", "pixeldrain.com"]):
                                return ShortlinkResult(
                                    original_url=url,
                                    resolved_url=str(post_resp.url),
                                    gate_type=GateType.AD_GATE,
                                    success=True,
                                    duration=time.time() - start_time,
                                    solver_used="cloud_drive_form_post",
                                    intermediate_urls=intermediates
                                )

                            urls = re.findall(r'https?://[^\s"\'<>]+', post_resp.text)
                            for u in urls:
                                if any(dest in u for dest in ["drive.google.com", "mega.nz", "pixeldrain.com"]):
                                    intermediates.append(u)
                                    return ShortlinkResult(
                                        original_url=url,
                                        resolved_url=u,
                                        gate_type=GateType.AD_GATE,
                                        success=True,
                                        duration=time.time() - start_time,
                                        solver_used="cloud_drive_form_post",
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
            error="Cloud Drive Gate solver could not resolve destination storage URL"
        )
