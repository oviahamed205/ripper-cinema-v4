"""
Voe.sx Video Host Decoder.
Decodes HLS master playlist URL from Base64 reversed payload.
"""
from __future__ import annotations

import base64
import re
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from ..base_decoder import BaseHostDecoder, StreamInfo


class VoeDecoder(BaseHostDecoder):
    name = "voe"
    priority = 25

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        return "voe.sx" in url.lower() or "voe-network" in url.lower()

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            page_html = resp.text

            # Voe encodes HLS playlist in a script tag
            m = re.search(r'let\s+sources\s*=\s*\{["\x27]hls["\x27]:\s*["\x27]([^"\x27]+)["\x27]', page_html)
            if m:
                raw_hls = m.group(1)
                # Decode Base64 if needed
                if not raw_hls.startswith("http"):
                    try:
                        decoded = base64.b64decode(raw_hls).decode("utf-8")
                        raw_hls = decoded
                    except Exception:
                        pass

                return StreamInfo(
                    stream_url=raw_hls,
                    headers={"Referer": url},
                    quality="1080p",
                    format="hls",
                    host_name="Voe",
                )

        return None