"""
ripper.portals.fourkhdhub
~~~~~~~~~~~~~~~~~~~~~~~~~

4KHDHub and HubCloud deep stream resolver.
Reverse-engineered from MovieBox-Tui fourkhdhub and HubCloud unrolling:
- Resolves multi-tiered drive and download gateway links
- Extracts direct PixelDrain API endpoints (pixeldrain.com/api/file/{id})
- Unrolls HubCloud php gateways, gamerxyt.com, and direct cloud streams
- Provides fallback direct stream resolution for movies and series.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import List, Optional, Tuple, Dict, Any
from bs4 import BeautifulSoup
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get


class FourKHdHubPortal(BasePortalResolver):
    """
    4KHDHub & HubCloud gateway resolver with automatic PixelDrain & cloud extraction.
    """

    @property
    def name(self) -> str:
        return "4KHDHub / HubCloud"

    @property
    def supported_domains(self) -> List[str]:
        return [
            "4khdhub",
            "hubcloud",
            "gamerxyt",
            "kmhd",
            "vcloud",
        ]

    @staticmethod
    def extract_pixeldrain_id(url: str) -> Optional[str]:
        """Extract file ID from any pixeldrain URL format."""
        m = re.search(r'pixeldrain\.com/(?:u|api/file)/([a-zA-Z0-9_-]+)', url)
        return m.group(1) if m else None

    @staticmethod
    def pixeldrain_to_api_url(url: str) -> str:
        """Convert pixeldrain webpage URL to direct binary stream API URL."""
        file_id = FourKHdHubPortal.extract_pixeldrain_id(url)
        if file_id:
            return f"https://pixeldrain.com/api/file/{file_id}"
        return url

    @staticmethod
    def unwrap_watch_online_url(href: str) -> Optional[str]:
        """Extract destination URL if wrapped inside query params or base64."""
        parsed = urllib.parse.urlparse(href)
        q = urllib.parse.parse_qs(parsed.query)
        for param in ("url", "link", "target", "dest"):
            if param in q and q[param]:
                val = q[param][0]
                if val.startswith("http://") or val.startswith("https://"):
                    return val
        return None

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        """Cascade through HubCloud landing pages and extract direct playable media URLs."""
        results: List[PortalStreamResult] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            resp = await client.get(url, headers=headers, follow_redirects=True, timeout=10.0)
            if resp.status_code != 200:
                return results

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # 1. Check if direct PixelDrain links exist in page scripts or links
            for script in soup.find_all("script"):
                stext = script.string or ""
                for pd_match in re.finditer(r'https?://(?:www\.)?pixeldrain\.com/(?:u|api/file)/([a-zA-Z0-9_-]+)', stext):
                    direct_api = f"https://pixeldrain.com/api/file/{pd_match.group(1)}"
                    results.append(
                        PortalStreamResult(
                            direct_url=direct_api,
                            resolution="1080p",
                            portal_name="4KHDHub (PixelDrain)",
                            is_hls=False,
                        )
                    )

            # 2. Extract intermediate HubCloud / download buttons
            download_links: List[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href.startswith("http"):
                    continue

                if any(x in href for x in ("hubcloud.php", "gamerxyt.com", "/download/")):
                    download_links.append(href)

                # Check for direct file lockers / CDN hosts
                if "pixeldrain.com" in href:
                    direct_pd = self.pixeldrain_to_api_url(href)
                    results.append(
                        PortalStreamResult(
                            direct_url=direct_pd,
                            resolution="1080p",
                            portal_name="4KHDHub (PixelDrain)",
                            is_hls=False,
                        )
                    )
                elif any(h in href for h in ("gofile.io", "streamtape.com", "doodstream", "streamwish")):
                    results.append(
                        PortalStreamResult(
                            direct_url=href,
                            resolution="1080p",
                            portal_name="4KHDHub (Cloud Mirror)",
                            is_hls=".m3u8" in href,
                        )
                    )

            # 3. Follow first intermediate HubCloud link if no direct streams found yet
            if not results and download_links:
                first_target = download_links[0]
                sub_resp = await client.get(first_target, headers=headers, follow_redirects=True, timeout=8.0)
                if sub_resp.status_code == 200:
                    sub_soup = BeautifulSoup(sub_resp.text, "html.parser")
                    for a in sub_soup.find_all("a", href=True):
                        href = a["href"].strip()
                        unwrapped = self.unwrap_watch_online_url(href) or href
                        if "pixeldrain.com" in unwrapped:
                            direct_pd = self.pixeldrain_to_api_url(unwrapped)
                            results.append(
                                PortalStreamResult(
                                    direct_url=direct_pd,
                                    resolution="1080p",
                                    portal_name="4KHDHub (PixelDrain)",
                                    is_hls=False,
                                )
                            )
                        elif unwrapped.endswith((".mp4", ".mkv", ".m3u8")):
                            results.append(
                                PortalStreamResult(
                                    direct_url=unwrapped,
                                    resolution="1080p",
                                    portal_name="4KHDHub (Direct Stream)",
                                    is_hls=".m3u8" in unwrapped,
                                )
                            )

        except Exception:
            pass

        # Deduplicate by direct_url
        seen = set()
        deduped = []
        for r in results:
            if r.direct_url not in seen:
                seen.add(r.direct_url)
                deduped.append(r)
        return deduped
