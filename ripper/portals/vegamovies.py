"""
VegaMovies & V-Cloud Modular Resolver.
Implements Jekop HLS playlist API and V-Cloud token decrypter.
"""

from __future__ import annotations

import re
from typing import List, Optional
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get


class VegaMoviesPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "VegaMovies / V-Cloud"

    @property
    def supported_domains(self) -> List[str]:
        return ["vegamovies", "vcloud", "fastcloud", "v-cloud"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            resp = await client.get(url, timeout=5.0)
            text = resp.text

            # 1. Check for Jekop Player direct HLS playlist API: GET /playlist/{file}.txt
            m_file = re.search(r"""file\s*:\s*["']~?([^"'\s]+)["']""", text)
            if m_file:
                file_id = m_file.group(1)
                from urllib.parse import urlparse
                parsed = urlparse(url)
                playlist_url = f"{parsed.scheme}://{parsed.netloc}/playlist/{file_id}.txt"
                p_resp = await client.get(playlist_url, timeout=4.0)
                if ".m3u8" in p_resp.text:
                    results.append(PortalStreamResult(
                        direct_url=playlist_url,
                        portal_name="VegaMovies Jekop HLS",
                        is_hls=True,
                    ))

            # 2. Check for V-Cloud / FastCloud download anchors
            for m_anchor in re.finditer(r"""<a\s+[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>""", text, re.DOTALL | re.IGNORECASE):
                href = m_anchor.group(1)
                label = m_anchor.group(2)
                if any(k in href for k in ("vcloud", "fastcloud", "pixeldrain", "workers.dev", "drive")):
                    results.append(PortalStreamResult(
                        direct_url=href,
                        filename=re.sub(r'<[^>]+>', '', label).strip() or None,
                        portal_name=self.name,
                    ))
        except Exception:
            pass
        return results
