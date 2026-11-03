"""
FileLions / FileMoon / StreamWish Decoder.
Unpacks Dean Edwards P.A.C.K.E.R. JavaScript to extract master HLS / MP4 stream.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from ..base_decoder import BaseHostDecoder, StreamInfo
from ...remote_hub import unpack_packer

LIONS_DOMAINS = ("filelions", "filemoon", "streamwish", "streamvid", "wolfstream")


class FileLionsDecoder(BaseHostDecoder):
    name = "filelions"
    priority = 25

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        return any(d in low for d in LIONS_DOMAINS)

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            page_html = resp.text

            # Check if packed JavaScript exists: eval(function(p,a,c,k,e,d)...)
            if "eval(function(p,a,c,k,e" in page_html:
                unpacked = unpack_packer(page_html)
                if unpacked:
                    # Look for m3u8 or mp4 links in unpacked code
                    m = re.search(r'["\x27](https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)["\x27]', unpacked)
                    if m:
                        stream_url = m.group(1)
                        return StreamInfo(
                            stream_url=stream_url,
                            headers={"Referer": url},
                            quality="1080p" if "1080" in stream_url else "HD",
                            format="hls" if ".m3u8" in stream_url else "mp4",
                            host_name="FileLions/FileMoon",
                        )

            # Direct regex match in raw HTML
            m_raw = re.search(r'file:\s*["\x27](https?://[^"\x27]+\.(?:m3u8|mp4)[^"\x27]*)["\x27]', page_html)
            if m_raw:
                stream_url = m_raw.group(1)
                return StreamInfo(
                    stream_url=stream_url,
                    headers={"Referer": url},
                    quality="HD",
                    format="hls" if ".m3u8" in stream_url else "mp4",
                    host_name="FileLions/FileMoon",
                )

        return None