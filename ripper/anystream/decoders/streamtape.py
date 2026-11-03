"""
StreamTape Video Host Decoder.
Parses hidden robotlink token from HTML DOM and returns direct MP4 stream.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from ..base_decoder import BaseHostDecoder, StreamInfo


class StreamTapeDecoder(BaseHostDecoder):
    name = "streamtape"
    priority = 25

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        return "streamtape.com" in url.lower() or "streamtape.to" in url.lower()

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            page_html = resp.text

            # Streamtape obfuscates the get_video link inside a JavaScript innerHTML concatenation
            m = re.search(r"document\.getElementById\(['\x22]ideoooolink['\x22]\)\.innerHTML\s*=\s*(.+?);", page_html)
            if not m:
                # Alternative regex
                m2 = re.search(r"['\x22]((?:https?:)?//(?:[^'\x22]+)/get_video\?[^'\x22]+)['\x22]", page_html)
                if m2:
                    raw_link = m2.group(1)
                    if raw_link.startswith("//"):
                        raw_link = "https:" + raw_link
                    return StreamInfo(
                        stream_url=raw_link,
                        headers={"Referer": url},
                        quality="HD",
                        format="mp4",
                        host_name="StreamTape",
                    )
                return None

            token_expr = m.group(1)
            parts = re.findall(r"['\x22]([^'\x22]+)['\x22]", token_expr)
            if parts:
                direct_url = "".join(parts)
                if direct_url.startswith("//"):
                    direct_url = "https:" + direct_url
                return StreamInfo(
                    stream_url=direct_url,
                    headers={"Referer": url},
                    quality="HD",
                    format="mp4",
                    host_name="StreamTape",
                )
        return None