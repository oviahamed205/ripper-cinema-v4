"""
MixDrop Video Host Decoder.
Extracts MDCore.vurl unpacked JavaScript parameter.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from ..base_decoder import BaseHostDecoder, StreamInfo
from ...remote_hub import unpack_packer


class MixDropDecoder(BaseHostDecoder):
    name = "mixdrop"
    priority = 25

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        return "mixdrop" in url.lower()

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            page_html = resp.text

            if "eval(function(p,a,c,k,e" in page_html:
                unpacked = unpack_packer(page_html)
                if unpacked:
                    m = re.search(r'(?:MDCore\.vurl|wurl|vurl)\s*=\s*["\x27]([^"\x27]+)["\x27]', unpacked)
                    if m:
                        stream_url = m.group(1)
                        if stream_url.startswith("//"):
                            stream_url = "https:" + stream_url
                        return StreamInfo(
                            stream_url=stream_url,
                            headers={"Referer": url},
                            quality="HD",
                            format="mp4",
                            host_name="MixDrop",
                        )

        return None