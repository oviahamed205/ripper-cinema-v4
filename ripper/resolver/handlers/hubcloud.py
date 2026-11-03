"""
HubCloud / CineCloud / NeoDrive / GamerXYT Gateway Handler.
Crawls multi-step server gates to extract direct Cloudflare R2 / S3 storage streams.
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
    _is_followable_http_url,
    is_direct_storage_url,
    is_direct_file_url,
    request_capped,
    request_capped_with_client,
)
from ...models import HopInfo, ServerMirror


HUBCLOUD_DOMAINS = (
    "hubcloud.club", "hubcloud.fit", "hubcloud.one", "hubcloud.dad",
    "hubcloud.link", "hubcloud.lol", "hubcloud.art", "hubcloud.yt",
    "hubcloud.cx", "hubcloud.vip", "vcloud.lol", "vcloud.link",
    "gamerxyt.com", "cinecloud.net", "cinecloud.site", "cinecloud.top", "neodrive.site",
)


def _first_anchor(soup: BeautifulSoup, pattern: str, base_url: str) -> Optional[str]:
    anchor = soup.find("a", href=re.compile(pattern, re.I))
    if not anchor:
        return None
    href = anchor.get("href") or ""
    joined = _clean_extracted_url(urllib.parse.urljoin(base_url, href))
    if _is_followable_http_url(joined):
        return joined
    return None


class HubCloudHandler(BaseResolverHandler):
    name = "hubcloud"
    priority = 20

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in HUBCLOUD_DOMAINS):
            return True
        if html and any(sig in html.lower() for sig in ("hubcloud", "gamerxyt", "cinecloud", "neodrive")):
            return True
        return False

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        low = url.lower()

        # Direct /d/ or /f/ CineCloud / NeoDrive endpoint
        if "/d/" in low or "/f/" in low or "generate.php" in low:
            direct_cloud = await self.extract_direct_cloud_from_d_endpoint(client, url, context.extra_headers, context.timeout)
            if direct_cloud and direct_cloud != url:
                hops.append(make_hop(
                    url=direct_cloud,
                    status_code=200,
                    redirect_type="cinecloud_r2_direct",
                    extra_details="Direct Cloudflare R2 / S3 stream extracted from /d/ endpoint",
                    hop_number=len(context.hops) + 1,
                ))
                return direct_cloud, hops

        try:
            page = await request_capped_with_client(client, url, context.extra_headers, context.timeout, follow_redirects=True)
            html = page.text or ""
            status = page.status_code

            hops.append(make_hop(
                url=url,
                status_code=status,
                redirect_type="hubcloud_landing",
                extra_details=f"HubCloud landing page fetched (status {status})",
                hop_number=len(context.hops) + 1,
            ))

            soup = BeautifulSoup(html, "html.parser")

            # 1. Check for GamerXYT generator link on hubcloud page
            gen_url = _first_anchor(soup, r"gamerxyt\.com/hubcloud\.php", str(page.url or url))
            
            # If current page IS ALREADY gamerxyt, or if gen_url was found, crawl it:
            target_gen_url = gen_url or (str(page.url or url) if "gamerxyt.com" in str(page.url or url) else None)
            if target_gen_url:
                ref_hdr = str(page.url or url) if gen_url else "https://hubcloud.cx/"
                gen_page = await request_capped_with_client(
                    client, target_gen_url, {**context.extra_headers, "Referer": ref_hdr}, context.timeout, follow_redirects=True
                )
                if gen_page.is_binary or is_direct_storage_url(gen_page.url) or is_direct_file_url(gen_page.url):
                    return gen_page.url, hops

                gen_html = gen_page.text or ""
                soup_gen = BeautifulSoup(gen_html, "html.parser")

                # A. Check for Cloudflare R2 / S3 in GamerXYT
                r2_url = _first_anchor(soup_gen, r"r2\.cloudflarestorage\.com|r2\.dev", str(gen_page.url or target_gen_url))
                if r2_url:
                    hops.append(make_hop(
                        url=r2_url,
                        status_code=200,
                        redirect_type="gamerxyt_r2_direct",
                        extra_details="Presigned R2 stream resolved via GamerXYT generator",
                        hop_number=len(context.hops) + 1,
                    ))
                    return r2_url, hops

                # B. Check for script-injected real PixelDrain link (e.g. var pxl = "https://pixeldrain.dev/u/...")
                m_pxl = re.search(r'var\s+pxl\s*=\s*["\x27]https?://pixeldrain\.(?:com|dev)/u/([a-zA-Z0-9_-]+)["\x27]', gen_html)
                if m_pxl:
                    px_id = m_pxl.group(1)
                    px_api = f"https://pixeldrain.com/api/file/{px_id}?download"
                    hops.append(make_hop(
                        url=px_api,
                        status_code=200,
                        redirect_type="gamerxyt_pixeldrain_direct",
                        extra_details=f"Extracted dynamic PixelDrain direct download stream: {px_id}",
                        hop_number=len(context.hops) + 1,
                    ))
                    return px_api, hops

                # C. Check anchor links on gamerxyt
                for a_gen in soup_gen.find_all("a", href=True):
                    g_href = a_gen["href"].strip()
                    if is_direct_storage_url(g_href) or is_direct_file_url(g_href):
                        return g_href, hops

            # 2. Search for direct stream or download anchor on hubcloud page
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in ("fast cloud", "download [fast", "hubcloud download", "direct download")):
                    if href.startswith("http"):
                        hops.append(make_hop(
                            url=href,
                            status_code=status,
                            redirect_type="hubcloud_button",
                            extra_details=f"Found button action: {text}",
                            hop_number=len(context.hops) + 1,
                        ))
                        return href, hops

            # 3. Check for JS token redirect
            match_token = re.search(r'var\s+link\s*=\s*["\x27](https?://[^"\x27]+)["\x27]', html)
            if match_token:
                target = match_token.group(1)
                hops.append(make_hop(
                    url=target,
                    status_code=status,
                    redirect_type="gamerxyt_js_token",
                    extra_details="Extracted GamerXYT JS link",
                    hop_number=len(context.hops) + 1,
                ))
                return target, hops

            # 4. Check for direct R2 link in page text
            match_r2 = re.search(r'https?://[a-zA-Z0-9.\-]+\.r2\.dev/[^\s"\'<>]+', html)
            if not match_r2:
                match_r2 = re.search(r'https?://[a-zA-Z0-9.\-]+\.r2\.cloudflarestorage\.com/[^\s"\'<>]+', html)
            if match_r2:
                r2_url = match_r2.group(0)
                hops.append(make_hop(
                    url=r2_url,
                    status_code=status,
                    redirect_type="r2_stream",
                    extra_details="Direct Cloudflare R2 stream detected",
                    hop_number=len(context.hops) + 1,
                ))
                return r2_url, hops

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="hubcloud_error",
                extra_details=f"HubCloud error: {exc}",
                hop_number=len(context.hops) + 1,
            ))

        return None

    async def extract_direct_cloud_from_d_endpoint(
        self,
        client: Any,
        d_url: str,
        headers: Dict[str, str],
        timeout: float = 6.0,
    ) -> Optional[str]:
        """Fetch a CineCloud / NeoDrive /d/{id} page and resolve presigned R2/S3 stream."""
        if not d_url:
            return None
        page = await request_capped_with_client(client, d_url, headers, timeout, follow_redirects=True)
        final_url = page.url or d_url
        if page.is_binary or is_direct_storage_url(final_url) or is_direct_file_url(final_url):
            return final_url

        html_body = page.text or ""
        m_r2 = re.search(r'https?://[a-zA-Z0-9.\-]+(?:\.r2\.cloudflarestorage\.com|\.r2\.dev)/[^\s"\'<>\\]+', html_body)
        if m_r2:
            return _clean_extracted_url(m_r2.group(0))

        # Check CineCloud /unlock endpoint to extract direct storage servers
        if "cinecloud" in d_url.lower():
            try:
                unlock_url = d_url.rstrip("/") + "/unlock"
                req_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                    "Referer": d_url,
                    "Origin": "https://cinecloud.top",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                }
                async with httpx.AsyncClient(http2=False, timeout=timeout, follow_redirects=True, verify=False) as h1_client:
                    unlocked = await h1_client.post(unlock_url, data={}, headers=req_headers)
                    if unlocked.status_code == 200:
                        import json
                        u_data = unlocked.json() if "application/json" in (unlocked.headers.get("content-type") or "") else json.loads(unlocked.text or "{}")
                        u_soup = BeautifulSoup(u_data.get("html", ""), "html.parser")
                        for a in u_soup.find_all("a", href=True):
                            s_href = a["href"]
                            if s_href.startswith("/"):
                                s_href = "https://cinecloud.top" + s_href
                            s_page = await h1_client.get(s_href, headers=req_headers)
                            s_url = str(s_page.url or s_href)
                            if (is_direct_storage_url(s_url) or is_direct_file_url(s_url)) and s_page.status_code in (200, 206):
                                return s_url
                            m_sr2 = re.search(r'https?://[a-zA-Z0-9.\-]+(?:\.r2\.cloudflarestorage\.com|\.r2\.dev)/[^\s"\'<>\\]+', s_page.text or "")
                            if m_sr2:
                                return _clean_extracted_url(m_sr2.group(0))
            except Exception:
                pass

        soup = BeautifulSoup(html_body, "html.parser")
        generate_href = _first_anchor(soup, r"generate\.php|/generate", final_url)
        if generate_href and generate_href != d_url:
            generated = await request_capped_with_client(
                client, generate_href, {**headers, "Referer": final_url}, timeout, follow_redirects=True
            )
            if generated.is_binary or is_direct_storage_url(generated.url) or is_direct_file_url(generated.url):
                return generated.url
            m_gen_r2 = re.search(r'https?://[a-zA-Z0-9.\-]+(?:\.r2\.cloudflarestorage\.com|\.r2\.dev)/[^\s"\'<>\\]+', generated.text or "")
            if m_gen_r2:
                return _clean_extracted_url(m_gen_r2.group(0))

        return None

    def extract_mirrors(self, html: str, base_url: str) -> List[ServerMirror]:
        mirrors: List[ServerMirror] = []
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not href or href.startswith(("#", "javascript:")):
                continue
            full_url = urllib.parse.urljoin(base_url, href)
            low_text = text.lower()
            if any(k in low_text for k in ("fast cloud", "hubcloud", "pixeldrain", "gofile", "drive", "download")):
                direct = full_url if is_direct_storage_url(full_url) or is_direct_file_url(full_url) else None
                mirrors.append(ServerMirror(
                    label=text or "HubCloud Mirror",
                    intermediate_url=full_url,
                    direct_download_url=direct,
                    server_type="Cloudflare R2 / S3" if direct else "HubCloud Mirror",
                ))
        return mirrors