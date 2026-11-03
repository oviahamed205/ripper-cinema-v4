"""
KatMovieHD / KMHD SvelteKit Gateway Handler.
Unlocks links.kmhd.eu SvelteKit SSR JSON payloads and extracts direct HubCloud / R2 stream mirrors.
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    coerce_timeout,
    host_of,
    parse_kmhd_sveltekit_data,
    request_capped_with_client,
)
from ...models import HopInfo, ServerMirror


KMHD_DOMAINS = ("kmhd.eu", "links.kmhd.eu", "links.kmhd.me", "kmhd.me", "katmoviehd")


async def resolve_kmhd_page(
    client: Optional[httpx.AsyncClient],
    kmhd_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
) -> List[ServerMirror]:
    """Unlock and parse links.kmhd.eu page to server mirrors with direct HubCloud R2 stream."""
    mirrors: List[ServerMirror] = []
    try:
        page = await request_capped_with_client(client, kmhd_url, headers, timeout, follow_redirects=True)
        soup = BeautifulSoup(page.text or "", "html.parser")
        form = soup.find("form")
        post_action = form.get("action") if form else "?/unlock"
        post_url = urllib.parse.urljoin(str(page.url or kmhd_url), post_action or "?/unlock")

        origin = f"{urllib.parse.urlparse(str(page.url or kmhd_url)).scheme}://{host_of(page.url or kmhd_url)}"
        post_headers = {
            **headers,
            "Origin": origin,
            "Referer": str(page.url or kmhd_url),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        timeout_obj = coerce_timeout(timeout)
        active = client
        close_after = False
        if active is None:
            active = httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True)
            close_after = True
        try:
            posted = await active.post(post_url, headers=post_headers, data={}, timeout=timeout_obj)
            body = getattr(posted, "text", "") or ""
        finally:
            if close_after:
                await active.aclose()

        file_name, server_links = parse_kmhd_sveltekit_data(body)
        for label, link in server_links:
            direct_url = None
            if "pixeldrain" in link:
                m_px = urllib.parse.urlparse(link).path.split("/")[-1]
                if m_px:
                    direct_url = f"https://pixeldrain.com/api/file/{m_px}?download"
            mirrors.append(
                ServerMirror(
                    label=f"KatMovieHD [{label}]",
                    intermediate_url=link,
                    direct_download_url=direct_url,
                    server_type="Cloudflare R2 / S3 Stream" if direct_url else f"{label} Mirror",
                    file_name=file_name,
                )
            )
        mirrors.sort(key=lambda item: bool(item.direct_download_url), reverse=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return mirrors
    return mirrors


class KMHDHandler(BaseResolverHandler):
    name = "kmhd"
    priority = 21

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in KMHD_DOMAINS):
            return True
        if html and ("kmhd" in html.lower() or "katmoviehd" in html.lower()):
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
            mirrors = await resolve_kmhd_page(client, url, context.extra_headers, timeout=context.timeout)
            if mirrors:
                best = mirrors[0]
                target_url = best.direct_download_url or best.intermediate_url
                hops.append(make_hop(
                    url=target_url,
                    status_code=200,
                    redirect_type="kmhd_unlock",
                    extra_details=f"Unlocked KMHD SvelteKit: {best.label}",
                    hop_number=len(context.hops) + 1,
                ))
                return target_url, hops
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="kmhd_error",
                extra_details=f"KMHD unlock error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None