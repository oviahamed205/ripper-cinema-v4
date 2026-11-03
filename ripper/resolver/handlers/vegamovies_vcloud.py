"""
VegaMovies / VCloud / FastDL Specialized Handler.
Deobfuscates multi-step countdown landing pages and FastDL buttons.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ...models import HopInfo, ServerMirror


class VegaMoviesVCloudHandler(BaseResolverHandler):
    name = "vegamovies_vcloud"
    priority = 22

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(k in low for k in ("fastdl", "vcloud", "vegamovies", "vgmlinks", "v-cloud")):
            return True
        if html and ("fastdl" in html.lower() or "vegamovies" in html.lower()):
            return True
        return False

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        try:
            resp = await client.get(url, headers=context.extra_headers, timeout=context.timeout)
            html = resp.text
            status = resp.status_code

            hops.append(make_hop(url=url, status_code=status, redirect_type="vegamovies_landing", extra_details="VegaMovies/FastDL page fetched"))

            soup = BeautifulSoup(html, "html.parser")

            # Look for fastdl / vcloud links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True).lower()
                if any(ign in text for ign in ("how to download", "tutorial", "watch video", "help", "guide")):
                    continue
                if any(kw in text for kw in ("v-cloud", "fastdl", "download now", "direct download", "g-direct", "filepress")):
                    if href.startswith("http"):
                        hops.append(make_hop(url=href, status_code=status, redirect_type="vcloud_button", extra_details=f"Target: {text}"))
                        return href, hops

            # Match embedded vcloud or r2 link in scripts
            m = re.search(r'https?://[a-zA-Z0-9.\-]+vcloud[a-zA-Z0-9.\-]*/[^\s"\'<>]+', html)
            if m:
                target = m.group(0)
                hops.append(make_hop(url=target, status_code=status, redirect_type="vcloud_regex", extra_details="Found embedded VCloud URL"))
                return target, hops

        except Exception as exc:
            hops.append(make_hop(url=url, status_code=0, redirect_type="vegamovies_error", extra_details=str(exc)))

        return None