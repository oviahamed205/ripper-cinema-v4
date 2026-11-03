"""
Generic HTML5 Video Decoder.
Crawls <video>, <source>, and iframe tags for direct MP4 and M3U8 URLs.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup
import httpx

from ..base_decoder import BaseHostDecoder, StreamInfo


class HTML5GenericDecoder(BaseHostDecoder):
    name = "html5_generic"
    priority = 90

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        return True

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        page_html = html
        if not page_html:
            try:
                async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
                    resp = await client.get(url)
                    page_html = resp.text
            except Exception:
                return None

        soup = BeautifulSoup(page_html, "html.parser")

        # 1. <video src="...">
        for v in soup.find_all("video"):
            src = v.get("src", "")
            if src and src.startswith("http"):
                return StreamInfo(
                    stream_url=src,
                    headers={"Referer": url},
                    format="hls" if ".m3u8" in src else "mp4",
                    host_name="HTML5 Video",
                )
            for s in v.find_all("source"):
                ssrc = s.get("src", "")
                if ssrc and ssrc.startswith("http"):
                    return StreamInfo(
                        stream_url=ssrc,
                        headers={"Referer": url},
                        format="hls" if ".m3u8" in ssrc else "mp4",
                        host_name="HTML5 Source",
                    )

        # 2. Regex search for direct m3u8 or mp4 links in scripts
        m = re.search(r'["\x27](https?://[^\s"\'<>]+\.(?:m3u8|mp4)(?:\?[^\s"\'<>]*)?)["\x27]', page_html)
        if m:
            s_url = m.group(1)
            return StreamInfo(
                stream_url=s_url,
                headers={"Referer": url},
                format="hls" if ".m3u8" in s_url else "mp4",
                host_name="Embedded Stream",
            )

        # 3. Dynamic Wire-Level Packet Sniffing via Camoufox Anti-Detect
        try:
            from ...healer import CamoufoxStreamSniffer
            sniffer = CamoufoxStreamSniffer()
            sniffed_items = await sniffer.sniff_and_extract(url, timeout=12.0)
            if sniffed_items:
                top_stream = sniffed_items[0].short_link or sniffed_items[0].unshortened_landing_url
                if top_stream:
                    return StreamInfo(
                        stream_url=top_stream,
                        headers={"Referer": url},
                        quality=sniffed_items[0].quality or "1080p",
                        format="hls" if ".m3u8" in top_stream else "mp4",
                        host_name="Camoufox Wire Stream",
                        title=sniffed_items[0].movie_name or "Direct Stream",
                    )
        except Exception:
            pass

        return None