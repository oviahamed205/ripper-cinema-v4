"""
VegaMovies NexDrive Form Automation & Generator Handler.
Crawls NexDrive landing pages and resolves underlying V-Cloud / HubCloud streams.
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
from ..core.honeypot_filter import is_ad_trap
from .vcloud import resolve_vcloud_page
from ...models import HopInfo, ServerMirror


NEXDRIVE_DOMAINS = ("nexdrive", "nexdrive.beer", "nexdrive.site", "nexdrive.pro", "nexdrive.xyz", "nexdrive.love", "nexdrive.fit")


async def resolve_fastdl_page(
    client: Optional[httpx.AsyncClient],
    fastdl_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
) -> Optional[ServerMirror]:
    """Resolve FastDL (G-Direct Instant) embed page to direct Google UserContent stream."""
    try:
        req_headers = dict(headers or {})
        req_headers["Referer"] = fastdl_url
        page = await request_capped_with_client(client, fastdl_url, req_headers, timeout, follow_redirects=True)
        html = page.text or ""
        m_link = re.search(r'dl\.php\?link=(https?://[^\s"\';]+)', html)
        if not m_link:
            m_link = re.search(r'["\x27](https?://video-downloads\.googleusercontent\.com/[^\s"\x27]+)["\x27]', html)
        if m_link:
            direct_url = _clean_extracted_url(m_link.group(1))
            return ServerMirror(
                label="G-Direct [Instant 10Gbps]",
                intermediate_url=fastdl_url,
                direct_download_url=direct_url,
                file_name="direct_video.mkv",
                server_type="Google High-Speed Direct",
            )
        m_reurl = re.search(r'var\s+reurl\s*=\s*["\x27](https?://[^\s"\x27]+)["\x27]', html)
        if m_reurl:
            reurl = m_reurl.group(1)
            m_sub = re.search(r'link=(https?://[^\s"\'&]+)', reurl)
            direct_u = _clean_extracted_url(m_sub.group(1)) if m_sub else _clean_extracted_url(reurl)
            return ServerMirror(
                label="G-Direct [Instant 10Gbps]",
                intermediate_url=fastdl_url,
                direct_download_url=direct_u,
                file_name="direct_video.mkv",
                server_type="Google High-Speed Direct",
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    return None


async def resolve_nexdrive_page(
    client: Optional[httpx.AsyncClient],
    nexdrive_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
) -> List[ServerMirror]:
    """Fetch VegaMovies NexDrive landing page and resolve underlying V-Cloud / G-Direct stream mirrors."""
    mirrors: List[ServerMirror] = []
    try:
        page = await request_capped_with_client(client, nexdrive_url, headers, timeout, follow_redirects=True)
        soup = BeautifulSoup(page.text or "", "html.parser")
        base = str(page.url or nexdrive_url)
        server_pat = re.compile(r"vcloud|hubcloud|fast-?dl|vgmlinks|filepress|filebee|dropgalaxy|dgdrive|gdtot", re.I)
        drive_links = soup.find_all("a", href=server_pat)
        seen: set[str] = set()
        for anchor in drive_links:
            href = anchor.get("href", "") or ""
            nested_url = _clean_extracted_url(urllib.parse.urljoin(base, href))
            if not nested_url or nested_url in seen or is_ad_trap(nested_url) or "vglist" in nested_url.lower():
                continue
            seen.add(nested_url)
            label = anchor.get_text(strip=True) or "Download Server"

            if re.search(r"fast-?dl", nested_url, re.I):
                fast_mirror = await resolve_fastdl_page(client, nested_url, headers, timeout=timeout)
                if fast_mirror:
                    mirrors.append(fast_mirror)
                else:
                    mirrors.append(ServerMirror(
                        label="G-Direct [Instant FastDL]",
                        intermediate_url=nested_url,
                        server_type="Google High-Speed Direct",
                    ))
            elif re.search(r"vcloud", nested_url, re.I):
                sub_mirrors = await resolve_vcloud_page(client, nested_url, headers, timeout=timeout)
                if sub_mirrors:
                    mirrors.extend(sub_mirrors)
                else:
                    mirrors.append(ServerMirror(
                        label="V-Cloud [Resumable Stream]",
                        intermediate_url=nested_url,
                        server_type="Cloud Stream Mirror",
                    ))
            elif re.search(r"filepress|filebee", nested_url, re.I):
                mirrors.append(ServerMirror(
                    label="Filepress [G-Drive Mirror]",
                    intermediate_url=nested_url,
                    server_type="Google Drive Mirror",
                ))
            elif re.search(r"gdtot", nested_url, re.I):
                mirrors.append(ServerMirror(
                    label="GDToT [G-Drive Mirror]",
                    intermediate_url=nested_url,
                    server_type="Google Drive Mirror",
                ))
            elif re.search(r"dropgalaxy|dgdrive", nested_url, re.I):
                mirrors.append(ServerMirror(
                    label="DropGalaxy [Cloud Mirror]",
                    intermediate_url=nested_url,
                    server_type="Cloud Mirror",
                ))
            else:
                mirrors.append(ServerMirror(
                    label=label,
                    intermediate_url=nested_url,
                    server_type="Cloud Stream Mirror",
                ))

        mirrors.sort(key=lambda item: bool(item.direct_download_url), reverse=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return mirrors
    return mirrors


class NexDriveHandler(BaseResolverHandler):
    name = "nexdrive"
    priority = 26

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in NEXDRIVE_DOMAINS):
            return True
        if html and "nexdrive" in html.lower():
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
            mirrors = await resolve_nexdrive_page(client, url, context.extra_headers, timeout=context.timeout)
            if mirrors:
                best = mirrors[0]
                target_url = best.direct_download_url or best.intermediate_url
                hops.append(make_hop(
                    url=target_url,
                    status_code=200,
                    redirect_type="nexdrive_extract",
                    extra_details=f"Extracted NexDrive stream: {best.label}",
                    hop_number=len(context.hops) + 1,
                ))
                return target_url, hops
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="nexdrive_error",
                extra_details=f"NexDrive error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None

    def extract_mirrors(self, html: str, base_url: str) -> List[ServerMirror]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        mirrors: List[ServerMirror] = []
        server_pat = re.compile(r"vcloud|hubcloud|fast-?dl|vgmlinks|filepress|filebee|dropgalaxy|dgdrive|gdtot", re.I)
        for anchor in soup.find_all("a", href=server_pat):
            href = _clean_extracted_url(urllib.parse.urljoin(base_url, anchor.get("href", "") or ""))
            if href and not is_ad_trap(href) and "vglist" not in href.lower():
                label = anchor.get_text(strip=True) or "NexDrive Mirror"
                mirrors.append(ServerMirror(
                    label=label,
                    intermediate_url=href,
                    server_type="Cloud Stream Mirror",
                ))
        return mirrors