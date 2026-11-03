"""
BollyFlix Portal Resolver.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from .base import BasePortalResolver, PortalStreamResult, safe_get


class BollyFlixPortal(BasePortalResolver):
    portal_name = "BollyFlix"

    @property
    def name(self) -> str:
        return "BollyFlix"

    @property
    def supported_domains(self) -> List[str]:
        return ["bollyflix", "bollyflix.zip", "bollyflix.in", "bollyflix.org"]

    def can_handle(self, url: str) -> bool:
        return any(d in url.lower() for d in self.supported_domains)

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if any(k in href.lower() for k in ("hubcloud", "fastdl", "vcloud", "pixeldrain", "drive")):
                        results.append(PortalStreamResult(
                            direct_url=href,
                            portal_name=self.portal_name,
                            resolution="HD",
                        ))
        except Exception:
            pass
        return results