"""
DoodStream / D000d / Playmogo Video Host Decoder.
Computes pass_md5 token and injects required Cloudflare/Origin CDN headers.
"""
from __future__ import annotations

import re
import time
import random
import string
import urllib.parse
from typing import Any, Dict, Optional

import httpx
from ..base_decoder import BaseHostDecoder, StreamInfo

DOOD_DOMAINS = ("dood", "d000d", "d0000d", "ds2play", "dooodster", "playmogo")


class DoodStreamDecoder(BaseHostDecoder):
    name = "doodstream"
    priority = 20

    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        return any(d in low for d in DOOD_DOMAINS)

    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": url,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            page_html = resp.text

            # Match /pass_md5/ endpoint
            m = re.search(r"(/pass_md5/[^'\"]+)", page_html)
            if not m:
                return None

            pass_url = urllib.parse.urljoin(url, m.group(1))
            pass_resp = await client.get(pass_url, headers={"Referer": url})
            token_prefix = pass_resp.text.strip()

            if not token_prefix:
                return None

            # DoodStream salt calculation: random string + expiry timestamp
            random_salt = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            final_stream_url = f"{token_prefix}{random_salt}?token={m.group(1).split('/')[-1]}&expiry={int(time.time()*1000)}"

            return StreamInfo(
                stream_url=final_stream_url,
                headers={"Referer": url, "User-Agent": headers["User-Agent"]},
                quality="HD",
                format="mp4",
                host_name="DoodStream",
            )