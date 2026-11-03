"""
Paster.so & Paster.gg Dedicated Container & Paste Locker Solver.
Extracts target URLs and media links from Paster.so, Paster.gg, and Pasteshr lockers,
handling client-side rendered pastes, decoded payloads, and raw API responses.
Implements both BaseAdGateSolver and BaseContainerUnroller protocols.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse
from typing import List, Optional

from bs4 import BeautifulSoup

from ripper.universal_bypasser.adgates.base import BaseAdGateSolver
from ripper.universal_bypasser.containers.base import BaseContainerUnroller
from ripper.universal_bypasser.models import ContainerResult, GateType, ShortlinkResult


class PasterSoSolver(BaseAdGateSolver, BaseContainerUnroller):
    """Solves and unrolls Paster.so / Paster.gg link lockers."""

    name: str = "paster_so"

    SUPPORTED_DOMAINS = {
        "paster.so",
        "paster.gg",
        "pasteshr.com",
    }

    async def _extract_all_links(self, url: str) -> tuple[List[str], str, List[str]]:
        intermediates = [url]
        found_links: List[str] = []
        folder_title = "Paster Locker"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with self.get_client(follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            intermediates.append(str(resp.url))
            html = resp.text

            # Extract title
            soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                folder_title = soup.title.string.strip()

            # 1. Look for Next.js props or JSON state
            m_props = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m_props:
                try:
                    data = json.loads(m_props.group(1))
                    page_props = data.get("props", {}).get("pageProps", {})
                    content = page_props.get("paste", {}).get("content", "") or page_props.get("content", "")
                    links = re.findall(r'https?://[^\s<>"\']+', content)
                    if links:
                        found_links.extend(links)
                except Exception:
                    pass

            # 2. Check API endpoint /api/paste/{id} or /raw/{id}
            if not found_links:
                parsed = urlparse(url)
                path_parts = [p for p in parsed.path.split("/") if p]
                if path_parts:
                    paste_id = path_parts[-1]
                    raw_url = f"{parsed.scheme}://{parsed.netloc}/raw/{paste_id}"
                    try:
                        raw_resp = await client.get(raw_url, headers=headers)
                        if raw_resp.status_code == 200:
                            links = re.findall(r'https?://[^\s<>"\']+', raw_resp.text)
                            if links:
                                found_links.extend(links)
                    except Exception:
                        pass

            # 3. DOM parsing for pre, code, or link containers
            if not found_links:
                pre_tags = soup.find_all(["pre", "code", "textarea", "div"], class_=re.compile(r"paste|content|text", re.I))
                for tag in pre_tags:
                    text_content = tag.get_text()
                    links = re.findall(r'https?://[^\s<>"\']+', text_content)
                    if links:
                        found_links.extend(links)

            # 4. Regex scan of entire HTML for external links
            if not found_links:
                all_urls = re.findall(r'https?://[^\s<>"\']+', html)
                valid_urls = [
                    u for u in all_urls
                    if not any(ign in u for ign in ["paster.", "pasteshr.", "google", "cloudflare", "schema.org", "w3.org", "favicon"])
                ]
                found_links.extend(valid_urls)

        # Deduplicate preserving order
        unique_links = list(dict.fromkeys(found_links))
        return unique_links, folder_title, intermediates

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        try:
            links, title, intermediates = await self._extract_all_links(url)
            if links:
                return ShortlinkResult(
                    original_url=url,
                    resolved_url=links[0],
                    gate_type=GateType.CONTAINER,
                    success=True,
                    duration=time.time() - start_time,
                    solver_used=self.name,
                    intermediate_urls=intermediates,
                )
        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=url,
                gate_type=GateType.CONTAINER,
                success=False,
                error=f"Paster.so solver error: {str(e)}",
                duration=time.time() - start_time,
                solver_used=self.name,
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=url,
            gate_type=GateType.CONTAINER,
            success=False,
            error="Could not extract links from Paster locker",
            duration=time.time() - start_time,
            solver_used=self.name,
        )

    async def unroll(self, url: str) -> ContainerResult:
        start_time = time.time()
        try:
            links, title, _ = await self._extract_all_links(url)
            return ContainerResult(
                container_url=url,
                title=title,
                gate_type=GateType.CONTAINER,
                unlocked_urls=links,
                success=len(links) > 0,
                duration=time.time() - start_time,
                solver_used=self.name,
            )
        except Exception as e:
            return ContainerResult(
                container_url=url,
                title="Paster Locker",
                gate_type=GateType.CONTAINER,
                unlocked_urls=[],
                success=False,
                duration=time.time() - start_time,
                solver_used=self.name,
                error=f"Paster.so unroll error: {str(e)}",
            )
