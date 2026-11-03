"""
KatmovieHD, CineFreak, and PixelDrain Modular Resolvers.
"""

from __future__ import annotations

import re
from typing import List, Optional
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get


class KatmovieHDPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "KatmovieHD / KatDrive"

    @property
    def supported_domains(self) -> List[str]:
        return ["katmoviehd", "katdrive", "kmhd"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            r = await client.get(url, timeout=5.0)
            # Find KatDrive or direct Cloudflare R2 links
            for m in re.finditer(r"""href=["'](https?://[^"']*(?:katdrive|r2\.cloudflarestorage|workers\.dev)[^"']*)["']""", r.text, re.IGNORECASE):
                results.append(PortalStreamResult(direct_url=m.group(1), portal_name=self.name))
        except Exception:
            pass
        return results


class CineFreakPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "CineFreak / CineCloud"

    @property
    def supported_domains(self) -> List[str]:
        return ["cinefreak", "cinecloud"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            r = await client.get(url, timeout=5.0)
            for m in re.finditer(r"""href=["'](https?://[^"']*(?:cinecloud|r2\.cloudflarestorage|pixeldrain)[^"']*)["']""", r.text, re.IGNORECASE):
                results.append(PortalStreamResult(direct_url=m.group(1), portal_name=self.name))
        except Exception:
            pass
        return results


class PixelDrainPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "PixelDrain FastDL"

    @property
    def supported_domains(self) -> List[str]:
        return ["pixeldrain.com"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        # Form direct API stream URL
        m = re.search(r'pixeldrain\.com/(?:u|api/file)/([a-zA-Z0-9]+)', url)
        if m:
            file_id = m.group(1)
            return [PortalStreamResult(
                direct_url=f"https://pixeldrain.com/api/file/{file_id}",
                portal_name=self.name,
            )]
        return []
