"""
Keeplinks Locker & Folder Unroller.
Extracts links from keeplinks.org / keeplinks.co protected folders.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ripper.universal_bypasser.containers.base import BaseContainerUnroller
from ripper.universal_bypasser.models import ContainerResult, GateType


class KeeplinksUnroller(BaseContainerUnroller):
    """Unrolls Keeplinks folders into clean hoster URLs."""

    name: str = "keeplinks"

    async def unroll(self, url: str) -> ContainerResult:
        start_time = time.time()
        unlocked: list[str] = []

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ContainerResult(
                        container_url=url,
                        gate_type=GateType.CONTAINER,
                        success=False,
                        duration=time.time() - start_time,
                        solver_used=self.name,
                        error=f"Keeplinks returned HTTP {resp.status_code}"
                    )

                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                title_el = soup.find("h1") or soup.find("title")
                title = title_el.text.strip() if title_el else "Keeplinks Folder"

                # Direct link extraction from <a> tags
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith(("http://", "https://")):
                        domain = urlparse(href).netloc.lower()
                        if "keeplinks" not in domain and not href.endswith((".css", ".js", ".png", ".jpg")):
                            if href not in unlocked:
                                unlocked.append(href)

                # Extraction from plain text or textarea
                for text_area in soup.find_all(["textarea", "pre"]):
                    urls = re.findall(r'https?://[^\s"\'<>]+', text_area.text)
                    for u in urls:
                        if "keeplinks" not in urlparse(u).netloc and u not in unlocked:
                            unlocked.append(u)

                # Extraction from JavaScript arrays
                js_links = re.findall(r'["\'](https?://[a-zA-Z0-9\.\-_/]+)["\']', html)
                for jl in js_links:
                    d = urlparse(jl).netloc.lower()
                    if "keeplinks" not in d and not jl.endswith((".js", ".css", ".png")):
                        if jl not in unlocked:
                            unlocked.append(jl)

                return ContainerResult(
                    container_url=url,
                    title=title,
                    gate_type=GateType.CONTAINER,
                    unlocked_urls=unlocked,
                    total_links=len(unlocked),
                    success=len(unlocked) > 0,
                    duration=time.time() - start_time,
                    solver_used=self.name
                )

        except Exception as e:
            return ContainerResult(
                container_url=url,
                gate_type=GateType.CONTAINER,
                success=False,
                duration=time.time() - start_time,
                solver_used=self.name,
                error=str(e)
            )
