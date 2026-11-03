"""
Pastebin, Linkbox & Text Locker Unroller.
Extracts batches of hoster links from Pastebin, Rentry.co, JustPaste.it, ControlC, and Linkbox.
"""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from ripper.universal_bypasser.containers.base import BaseContainerUnroller
from ripper.universal_bypasser.models import ContainerResult, GateType


class PastebinUnroller(BaseContainerUnroller):
    """Extracts download links from pastebin-style text lockers."""

    name: str = "pastebin_unroll"

    def _get_raw_url(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip("/")

        if "pastebin.com" in parsed.netloc and not path.startswith("raw/"):
            return f"https://pastebin.com/raw/{path}"
        if "rentry.co" in parsed.netloc and not path.startswith("raw/"):
            return f"https://rentry.co/raw/{path}"
        if "justpaste.it" in parsed.netloc and not path.startswith("raw/"):
            return f"https://justpaste.it/raw/{path}"
        return url

    async def unroll(self, url: str) -> ContainerResult:
        start_time = time.time()
        raw_target = self._get_raw_url(url)
        unlocked: list[str] = []

        try:
            async with self.get_client(follow_redirects=True) as client:
                resp = await client.get(raw_target)
                if resp.status_code != 200:
                    # Fallback to normal URL if raw failed
                    resp = await client.get(url)

                text = resp.text
                urls = re.findall(r'https?://[^\s"\'<>]+', text)

                for u in urls:
                    u_netloc = urlparse(u).netloc.lower()
                    if not any(paste in u_netloc for paste in ["pastebin", "rentry", "justpaste", "controlc"]):
                        if not u.endswith((".css", ".js", ".png", ".jpg")):
                            if u not in unlocked:
                                unlocked.append(u)

                return ContainerResult(
                    container_url=url,
                    title="Pastebin / Text Container",
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
