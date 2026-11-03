"""
VegaMovies / V-Cloud / FastDL Specialized Handler.
Unwraps nested atob() tokens and deobfuscates FastDL / Cloudflare R2 server mirrors.
"""
from __future__ import annotations

import asyncio
import base64
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    is_direct_storage_url,
    is_direct_file_url,
    request_capped_with_client,
)
from ...models import HopInfo, ServerMirror


VCLOUD_DOMAINS = ("vcloud.fit", "vcloud.lol", "vcloud.link", "vcloud.zip", "vcloud.you", "vegamovies", "vgmlinks", "fastdl", "v-cloud")


def _decode_vcloud_token(html_text: str) -> Optional[str]:
    """Unwrap atob(atob(...)) or atob(...) tokens used by V-Cloud protectors."""
    match = re.search(r'atob\(atob\([\'"]([a-zA-Z0-9+/=]+)[\'"]\)\)', html_text or "")
    if not match:
        match = re.search(r'atob\([\'"]([a-zA-Z0-9+/=]+)[\'"]\)', html_text or "")
    if not match:
        return None
    blob = match.group(1)
    try:
        first = base64.b64decode(blob).decode("utf-8", errors="ignore")
        if first.startswith("http"):
            return _clean_extracted_url(first)
        second = base64.b64decode(first).decode("utf-8", errors="ignore")
        if second.startswith("http"):
            return _clean_extracted_url(second)
    except Exception:
        return None
    return None


async def resolve_vcloud_page(
    client: Optional[httpx.AsyncClient],
    vcloud_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
) -> List[ServerMirror]:
    """Resolve VegaMovies V-Cloud protector using token unwrapping to Cloudflare R2 / S3 streams."""
    mirrors: List[ServerMirror] = []
    try:
        page = await request_capped_with_client(client, vcloud_url, headers, timeout, follow_redirects=True)
        token_url = _decode_vcloud_token(page.text or "") or vcloud_url

        if is_direct_storage_url(token_url) or is_direct_file_url(token_url):
            mirrors.append(
                ServerMirror(
                    label="VegaCloud Direct",
                    intermediate_url=token_url,
                    direct_download_url=token_url,
                    server_type="Cloudflare R2 Stream",
                )
            )
            return mirrors

        token_page = page
        if token_url != vcloud_url:
            token_page = await request_capped_with_client(
                client, token_url, {**headers, "Referer": vcloud_url}, timeout, follow_redirects=True
            )

        if token_page.is_binary or is_direct_storage_url(token_page.url) or is_direct_file_url(token_page.url):
            mirrors.append(
                ServerMirror(
                    label="VegaCloud Direct",
                    intermediate_url=token_url,
                    direct_download_url=token_page.url,
                    server_type="Cloudflare R2 Stream",
                )
            )
            return mirrors

        soup = BeautifulSoup(token_page.text or "", "html.parser")
        base = str(token_page.url or token_url)
        for anchor in soup.find_all("a"):
            label = (anchor.get_text() or "").strip()
            href = _clean_extracted_url(urllib.parse.urljoin(base, anchor.get("href", "") or ""))
            if not href:
                continue
            haystack = f"{label} {href}".lower()
            # Filter out non-download helper/tutorial/social anchors
            if any(ign in haystack for ign in ("how to download", "tutorial", "watch video", "join telegram", "help", "contact")):
                continue

            if not any(
                keyword in haystack
                for keyword in [
                    "download", "server", "fsl", "pixel", "gofile",
                    "10gbps", "r2.dev", "cloudflarestorage", "fast-dl",
                    "fastdl", "direct", "instant", "g-direct", "filepress",
                ]
            ):
                continue
            direct_url = None
            if is_direct_storage_url(href) or is_direct_file_url(href):
                direct_url = href
            elif "pixeldrain" in href:
                m_px = urllib.parse.urlparse(href).path.split("/")[-1]
                if m_px:
                    direct_url = f"https://pixeldrain.com/api/file/{m_px}?download"
            mirrors.append(
                ServerMirror(
                    label=f"VegaCloud [{label}]" if label else "VegaCloud Mirror",
                    intermediate_url=href,
                    direct_download_url=direct_url,
                    server_type="Cloudflare R2 Stream" if direct_url else "Download Mirror",
                )
            )
        # Check for direct R2 urls in HTML
        for match in re.finditer(r'https?://[a-zA-Z0-9.\-]+(?:\.r2\.cloudflarestorage\.com|\.r2\.dev)/[^\s"\'<>\\]+', token_page.text or ""):
            cloud_url = _clean_extracted_url(match.group(0))
            if not any(item.direct_download_url == cloud_url for item in mirrors):
                mirrors.append(
                    ServerMirror(
                        label="VegaCloud [R2]",
                        intermediate_url=token_url,
                        direct_download_url=cloud_url,
                        server_type="Cloudflare R2 Stream",
                    )
                )
        mirrors.sort(key=lambda item: bool(item.direct_download_url), reverse=True)
    except asyncio.CancelledError:
        raise
    except Exception:
        return mirrors
    return mirrors


class VCloudHandler(BaseResolverHandler):
    name = "vcloud"
    priority = 22

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in VCLOUD_DOMAINS):
            return True
        if html and any(sig in html.lower() for sig in ("vcloud", "vegamovies", "fastdl", "v-cloud")):
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
            mirrors = await resolve_vcloud_page(client, url, context.extra_headers, timeout=context.timeout)
            if mirrors:
                best = mirrors[0]
                target_url = best.direct_download_url or best.intermediate_url
                hops.append(make_hop(
                    url=target_url,
                    status_code=200,
                    redirect_type="vcloud_direct",
                    extra_details=f"Unwrapped VegaCloud: {best.label}",
                    hop_number=len(context.hops) + 1,
                ))
                return target_url, hops
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="vcloud_error",
                extra_details=f"V-Cloud error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None

    def extract_mirrors(self, html: str, base_url: str) -> List[ServerMirror]:
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        mirrors: List[ServerMirror] = []
        for anchor in soup.find_all("a", href=True):
            href = _clean_extracted_url(urllib.parse.urljoin(base_url, anchor.get("href", "") or ""))
            label = anchor.get_text(strip=True)
            haystack = f"{label} {href}".lower()
            if any(ign in haystack for ign in ("how to download", "tutorial", "watch video", "help", "guide")):
                continue
            if any(kw in haystack for kw in ("download", "server", "fsl", "pixel", "gofile", "10gbps", "r2.dev", "cloudflarestorage", "fast-dl", "fastdl", "filepress")):
                mirrors.append(ServerMirror(
                    label=label or "VegaCloud Mirror",
                    intermediate_url=href,
                    server_type="Cloud Stream Mirror",
                ))
        return mirrors