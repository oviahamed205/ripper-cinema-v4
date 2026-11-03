"""
OlaMovies / OMDrive Multi-Hop Gateway Handler.
Unpacks Next.js metadata, Turnstile challenges, and direct cdn-cgi storage mirrors.
"""
from __future__ import annotations

import asyncio
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    request_capped_with_client,
)
from ...models import HopInfo, ServerMirror


OLAMOVIES_DOMAINS = ("ol-am.top", "olamovies", "omdrive")


async def resolve_olamovies_page(
    client: Optional[httpx.AsyncClient],
    olamovies_url: str,
    headers: Dict[str, str],
    timeout: float = 12.0,
) -> List[ServerMirror]:
    """Unlock OlaMovies link generator and unpack Next.js metadata and direct streams."""
    mirrors: List[ServerMirror] = []
    target_url = olamovies_url
    if "ol-am.top" in target_url:
        target_url = target_url.replace("links.ol-am.top", "links.olamovies.mov")

    try:
        page = await request_capped_with_client(client, target_url, headers, timeout=timeout, follow_redirects=True)
        html_content = page.text or ""
        if not html_content:
            return mirrors

        # Extract filename & filesize from Next.js payload
        filename = ""
        m_fn = re.search(r'filename\\*"\s*:\s*\\*"([^\\"]+)', html_content)
        if m_fn:
            filename = m_fn.group(1).replace("\\", "").strip()

        soup = BeautifulSoup(html_content, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if any(h in href.lower() for h in ["hubcloud", "gofile", "pixeldrain", "workers.dev", "cdn-cgi/content", "serve?t="]):
                full_href = urllib.parse.urljoin(str(page.url or target_url), href)
                direct = full_href
                if "pixeldrain" in direct:
                    m_px = urllib.parse.urlparse(direct).path.split("/")[-1]
                    if m_px:
                        direct = f"https://pixeldrain.com/api/file/{m_px}?download"
                mirrors.append(
                    ServerMirror(
                        label=f"OlaMovies [{a.get_text().strip() or 'Direct'}]",
                        intermediate_url=full_href,
                        direct_download_url=direct,
                        file_name=filename or "olamovies_download.mkv",
                        server_type="OlaMovies Direct CDN",
                        is_resumable=True,
                    )
                )
        mirrors.sort(key=lambda item: bool(item.direct_download_url), reverse=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return mirrors
    return mirrors


class OlaMoviesHandler(BaseResolverHandler):
    name = "olamovies"
    priority = 27

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in OLAMOVIES_DOMAINS):
            return True
        if html and ("olamovies" in html.lower() or "omdrive" in html.lower()):
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
            mirrors = await resolve_olamovies_page(client, url, context.extra_headers, timeout=context.timeout)
            if mirrors:
                best = mirrors[0]
                target_url = best.direct_download_url or best.intermediate_url
                hops.append(make_hop(
                    url=target_url,
                    status_code=200,
                    redirect_type="olamovies_resolve",
                    extra_details=f"Extracted OlaMovies stream: {best.file_name or best.label}",
                    hop_number=len(context.hops) + 1,
                ))
                return target_url, hops
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="olamovies_error",
                extra_details=f"OlaMovies error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None