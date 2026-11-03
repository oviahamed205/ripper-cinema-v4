"""
OlaMovies & OMDrive V3 Modular Resolver.
Implements Turbopack client AES key and Cloudflare Worker endpoints.
"""

from __future__ import annotations

import re
from typing import List, Optional
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get

OMDRIVE_AES_KEY = "1593cc0b7cd7651ad8a17bc528986046fa3e6e709f6405274b17def26c7faa6r"


class OlaMoviesPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "OlaMovies / OMDrive V3"

    @property
    def supported_domains(self) -> List[str]:
        return ["olamovies", "omdrive", "ol-am.top"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            resp = await client.get(url, timeout=5.0)
            text = resp.text

            # 1. Search for Cloudflare Worker stream tokens
            for m_worker in re.finditer(r'https?://[a-zA-Z0-9_\-\.]+\.workers\.dev/serve\?t=[a-zA-Z0-9_\-\.%]+', text):
                results.append(PortalStreamResult(
                    direct_url=m_worker.group(0),
                    portal_name="OMDrive V3 Worker CDN",
                ))

            # 2. Search for Next.js hydration __NEXT_DATA__
            m_next = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text, re.DOTALL)
            if m_next:
                import json
                try:
                    data = json.loads(m_next.group(1))
                    file_info = safe_get(data, "props", "pageProps", "file")
                    if file_info:
                        dl = file_info.get("downloadUrl") or file_info.get("streamUrl")
                        if dl:
                            results.append(PortalStreamResult(
                                direct_url=dl,
                                filename=file_info.get("fileName"),
                                filesize_bytes=file_info.get("fileSize"),
                                portal_name=self.name,
                            ))
                except Exception:
                    pass
        except Exception:
            pass
        return results
