"""
AppDrive / JioDrive / DriveHub Token Handler.
Resolves tokenized Google Drive and high-speed Cloud CDN download links.
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    request_capped_with_client,
)
from ...models import HopInfo


APPDRIVE_DOMAINS = (
    "appdrive.info", "appdrive.in", "jiodrive.xyz", "drivehub.ws",
    "driveseed.org", "drivefire.co",
)


class AppDriveHandler(BaseResolverHandler):
    name = "appdrive"
    priority = 29

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in APPDRIVE_DOMAINS):
            return True
        if html and any(k in html.lower() for k in ("appdrive", "jiodrive", "drivehub", "driveseed")):
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
            page = await request_capped_with_client(client, url, context.extra_headers, timeout=context.timeout, follow_redirects=True)
            status = page.status_code
            html = page.text or ""

            hops.append(make_hop(
                url=url,
                status_code=status,
                redirect_type="appdrive_landing",
                extra_details=f"AppDrive gateway fetched (status {status})",
                hop_number=len(context.hops) + 1,
            ))

            soup = BeautifulSoup(html, "html.parser")
            base = str(page.url or url)

            # Look for instant download or direct CDN link
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in ("instant download", "drive download", "direct download", "download file", "fast download")):
                    full = _clean_extracted_url(urllib.parse.urljoin(base, href))
                    if _is_followable_http_url(full) and full != url:
                        hops.append(make_hop(
                            url=full,
                            status_code=status,
                            redirect_type="appdrive_button",
                            extra_details=f"Found action: {text}",
                            hop_number=len(context.hops) + 1,
                        ))
                        return full, hops

            # Check for form action
            for form in soup.find_all("form"):
                action = form.get("action", "")
                if action:
                    full_action = _clean_extracted_url(urllib.parse.urljoin(base, action))
                    if _is_followable_http_url(full_action) and full_action != url:
                        hops.append(make_hop(
                            url=full_action,
                            status_code=status,
                            redirect_type="appdrive_form",
                            extra_details="Extracted AppDrive form action",
                            hop_number=len(context.hops) + 1,
                        ))
                        return full_action, hops

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="appdrive_error",
                extra_details=f"AppDrive error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None