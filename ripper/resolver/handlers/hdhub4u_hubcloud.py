"""
HDHub4u / HubCloud Bridge Handler.
Navigates drive / token multi-step redirects on HDHub4u network.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ...models import HopInfo


class HDHub4uHandler(BaseResolverHandler):
    name = "hdhub4u_hubcloud"
    priority = 23

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        return any(k in low for k in ("hdhub4u", "hdhub", "hblinks", "hubdrive"))

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

            hops.append(make_hop(url=url, status_code=status, redirect_type="hdhub4u_landing", extra_details="HDHub4u gateway fetched"))

            # Check for hubcloud or drive links inside page
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if any(k in href for k in ("hubcloud", "gamerxyt", "vcloud", "drive")):
                    hops.append(make_hop(url=href, status_code=status, redirect_type="hdhub4u_target", extra_details="Discovered downstream HubCloud link"))
                    return href, hops

        except Exception as exc:
            hops.append(make_hop(url=url, status_code=0, redirect_type="hdhub4u_error", extra_details=str(exc)))

        return None