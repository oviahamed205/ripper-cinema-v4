"""
MagicLinks Countdown & Mirror Resolver Handler.
Decodes magiclinks.lol landing pages to high-speed PixelDrain / Cloud mirrors.
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    request_capped_with_client,
)
from ...models import HopInfo, ServerMirror


MAGICLINKS_DOMAINS = ("magiclinks.lol", "magiclinks.site", "magiclinks.co")


async def resolve_magiclinks_page(
    client: Optional[httpx.AsyncClient],
    magiclinks_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
) -> List[ServerMirror]:
    """Parse magiclinks.lol page to server mirrors with direct Pixeldrain stream."""
    mirrors: List[ServerMirror] = []
    try:
        page = await request_capped_with_client(client, magiclinks_url, headers, timeout, follow_redirects=True)
        soup = BeautifulSoup(page.text or "", "html.parser")
        base = str(page.url or magiclinks_url)
        for anchor in soup.find_all("a"):
            label = (anchor.get_text() or "").strip()
            href = _clean_extracted_url(urllib.parse.urljoin(base, anchor.get("href", "") or ""))
            if not href:
                continue
            haystack = f"{label} {href}".upper()
            if not any(
                keyword in haystack
                for keyword in [
                    "SKYDROP", "ONE CLICK", "TRANSFER", "PIXELDRAIN",
                    "GOFILE", "VIKINGFILE", "BUZZHIEVER", "FAST",
                ]
            ):
                continue
            direct_url = None
            if "pixeldrain" in href:
                m_px = urllib.parse.urlparse(href).path.split("/")[-1]
                if m_px:
                    direct_url = f"https://pixeldrain.com/api/file/{m_px}?download"
            mirrors.append(
                ServerMirror(
                    label=label or "MagicLinks Mirror",
                    intermediate_url=href,
                    direct_download_url=direct_url,
                    server_type="PixelDrain Direct Stream" if direct_url else "Download Mirror",
                )
            )
        mirrors.sort(key=lambda item: bool(item.direct_download_url), reverse=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return mirrors
    return mirrors


class MagicLinksHandler(BaseResolverHandler):
    name = "magiclinks"
    priority = 24

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in MAGICLINKS_DOMAINS):
            return True
        if html and "magiclinks" in html.lower():
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
            mirrors = await resolve_magiclinks_page(client, url, context.extra_headers, timeout=context.timeout)
            if mirrors:
                best = mirrors[0]
                target_url = best.direct_download_url or best.intermediate_url
                hops.append(make_hop(
                    url=target_url,
                    status_code=200,
                    redirect_type="magiclinks_unwrap",
                    extra_details=f"Unwrapped MagicLinks mirror: {best.label}",
                    hop_number=len(context.hops) + 1,
                ))
                return target_url, hops
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="magiclinks_error",
                extra_details=f"MagicLinks error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None