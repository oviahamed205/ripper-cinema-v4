"""
Video Hosts & Streaming Cluster Resolver Plugin for Ripper Resolver.
Provides pure-HTTP, zero-headless link resolution and HLS manifest extraction for:
- DoodStream (doodstream.com, dood.watch, dood.so, d0000d.com, ds2play.com)
- MixDrop (mixdrop.co, mixdrop.to, mixdrop.ch, mixdrop.sx, mixdrop.ag)
- StreamWish (streamwish.to, streamwish.com, wishembed.pro, ajcontent.net)
- Voe.sx (voe.sx, voe-unblock.com, reputationsparsenap.com)
- Filemoon (filemoon.sx, filemoon.to, filemoon.in, bysezejataos.com)
- Kwik / AnimePahe (kwik.cx)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import string
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    coerce_timeout,
    default_headers,
    extract_filename_from_url_or_headers,
    host_of,
    request_capped,
)
from ..core.packer_unpack import unpack_packer, detect_packed
from ...models import HopInfo, ServerMirror

logger = logging.getLogger(__name__)

DOODSTREAM_DOMAINS = (
    "doodstream.com", "dood.watch", "dood.so", "dood.to", "dood.la", "dood.ws",
    "d0000d.com", "d0o0d.com", "ds2play.com", "do0od.com", "dood.pm", "dood.re",
)

MIXDROP_DOMAINS = (
    "mixdrop.co", "mixdrop.to", "mixdrop.sx", "mixdrop.ch", "mixdrop.bz",
    "mixdrop.ag", "mixdrop.club", "mixdrop.cv", "mixdrop.ch",
)

STREAMWISH_DOMAINS = (
    "streamwish.to", "streamwish.com", "wishembed.pro", "ajcontent.net",
    "flaswish.com", "wishfast.top", "embedwish.com", "awish.pro", "streamwish.site",
)

VOE_DOMAINS = (
    "voe.sx", "voe-unblock.com", "reputationsparsenap.com", "audaciousdefaulthouse.com",
    "celebrateprofile.com", "tubesquared.com",
)

FILEMOON_DOMAINS = (
    "filemoon.sx", "filemoon.to", "filemoon.in", "filemoon.link", "bysezejataos.com",
)

KWIK_DOMAINS = (
    "kwik.cx",
)

VIDHIDE_DOMAINS = (
    "vidhide.com", "vidhidepro.com", "vidhideplus.com", "vidhidevip.com", "streamhide.to",
    "streamhide.com", "morencius.com",
)

LULUVDO_DOMAINS = (
    "luluvdo.com", "luluvdoo.com", "lulustream.com",
)



def _gen_random_token(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


class VideoHostsHandler(BaseResolverHandler):
    """Universal handler for embedded web video hosters."""
    name = "video_hosts"
    priority = 14  # Sits ahead of generic file lockers and ad shorteners

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in DOODSTREAM_DOMAINS):
            return True
        if any(d in low for d in MIXDROP_DOMAINS):
            return True
        if any(d in low for d in STREAMWISH_DOMAINS):
            return True
        if any(d in low for d in VOE_DOMAINS):
            return True
        if any(d in low for d in FILEMOON_DOMAINS):
            return True
        if any(d in low for d in KWIK_DOMAINS):
            return True
        if any(d in low for d in VIDHIDE_DOMAINS):
            return True
        if any(d in low for d in LULUVDO_DOMAINS):
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

        # 1. DoodStream Resolver
        if any(d in low for d in DOODSTREAM_DOMAINS):
            res = await self._resolve_doodstream(url, client, context, hops)
            if res:
                return res

        # 2. MixDrop Resolver
        if any(d in low for d in MIXDROP_DOMAINS):
            res = await self._resolve_mixdrop(url, client, context, hops)
            if res:
                return res

        # 3. StreamWish Resolver
        if any(d in low for d in STREAMWISH_DOMAINS):
            res = await self._resolve_streamwish(url, client, context, hops)
            if res:
                return res

        # 4. Voe.sx Resolver
        if any(d in low for d in VOE_DOMAINS):
            res = await self._resolve_voe(url, client, context, hops)
            if res:
                return res

        # 5. Filemoon Resolver
        if any(d in low for d in FILEMOON_DOMAINS):
            res = await self._resolve_filemoon(url, client, context, hops)
            if res:
                return res

        # 6. Kwik Resolver
        if any(d in low for d in KWIK_DOMAINS):
            res = await self._resolve_kwik(url, client, context, hops)
            if res:
                return res

        # 7. VidHide / StreamHide Resolver
        if any(d in low for d in VIDHIDE_DOMAINS):
            res = await self._resolve_vidhide(url, client, context, hops)
            if res:
                return res

        # 8. LuluVdo / LuluStream Resolver
        if any(d in low for d in LULUVDO_DOMAINS):
            res = await self._resolve_luluvdo(url, client, context, hops)
            if res:
                return res

        return None


    async def _resolve_doodstream(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        # Normalize embed URL
        embed_url = url
        if "/d/" in url:
            embed_url = url.replace("/d/", "/e/")

        host = host_of(embed_url) or "doodstream.com"
        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": embed_url,
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="doodstream_embed",
            extra_details=f"Fetched DoodStream embed page ({len(fetch.text)} bytes)",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        # Look for pass_md5 token call: $.get('/pass_md5/...', function(data) { ... })
        md5_match = re.search(r"/(?:pass_md5|pass_encrypted)/([a-zA-Z0-9_\-]+)", html)
        token_match = re.search(r"\?token=([a-zA-Z0-9_\-]+)&expiry=", html)

        if not md5_match:
            return None

        pass_path = md5_match.group(0)
        pass_url = f"https://{host}{pass_path}"

        pass_headers = {
            "User-Agent": headers["User-Agent"],
            "Referer": embed_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        pass_fetch = await request_capped(client, pass_url, headers=pass_headers, timeout=10.0)
        prefix = pass_fetch.text.strip()
        if not prefix or not prefix.startswith("http"):
            return None

        token_str = token_match.group(1) if token_match else _gen_random_token(10)
        expiry = int(time.time() * 1000)
        random_str = _gen_random_token(10)

        direct_stream_url = f"{prefix}{random_str}?token={token_str}&expiry={expiry}"
        hops.append(make_hop(
            url=direct_stream_url,
            status_code=200,
            redirect_type="doodstream_direct_stream",
            extra_details="Assembled authenticated DoodStream direct stream URL",
            hop_number=len(hops) + 1,
        ))
        return direct_stream_url, hops

    async def _resolve_mixdrop(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        embed_url = url
        if "/f/" in url:
            embed_url = url.replace("/f/", "/e/")

        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": "https://mixdrop.co/",
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="mixdrop_embed",
            extra_details="Fetched MixDrop player container",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        unpacked_code = ""
        if detect_packed(html):
            unpacked_code = unpack_packer(html)

        content = html + "\n" + unpacked_code
        match = re.search(r'MDCore\.wurl\s*=\s*["\']([^"\']+)["\']', content)
        if not match:
            match = re.search(r'(?:vskey|vurl)\s*=\s*["\']([^"\']+)["\']', content)

        if match:
            stream_url = match.group(1).strip()
            if stream_url.startswith("//"):
                stream_url = "https:" + stream_url
            elif not stream_url.startswith("http"):
                stream_url = f"https://{host_of(embed_url)}{stream_url}"

            hops.append(make_hop(
                url=stream_url,
                status_code=200,
                redirect_type="mixdrop_direct_stream",
                extra_details="Extracted MDCore video stream from packed JS",
                hop_number=len(hops) + 1,
            ))
            return stream_url, hops

        return None

    async def _resolve_streamwish(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        embed_url = url
        if "/f/" in url:
            embed_url = url.replace("/f/", "/e/")

        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": "https://streamwish.to/",
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="streamwish_embed",
            extra_details="Fetched StreamWish player",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        unpacked = unpack_packer(html) if detect_packed(html) else ""
        content = html + "\n" + unpacked

        m3u8_match = re.search(r'sources:\s*\[\{[^}]*file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', content)
        if not m3u8_match:
            m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)

        if m3u8_match:
            m3u8_url = m3u8_match.group(1).strip()
            hops.append(make_hop(
                url=m3u8_url,
                status_code=200,
                redirect_type="streamwish_hls_stream",
                extra_details="Extracted StreamWish Master HLS manifest URL",
                hop_number=len(hops) + 1,
            ))
            return m3u8_url, hops

        return None

    async def _resolve_voe(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        embed_url = url
        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": embed_url,
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="voe_embed",
            extra_details="Fetched Voe.sx page",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        # Check for window.location redirect inside script
        redir_match = re.search(r'window\.location\.href\s*=\s*["\']([^"\']+)["\']', html)
        if redir_match:
            next_target = redir_match.group(1).strip()
            if next_target.startswith("http") and next_target != embed_url:
                fetch = await request_capped(client, next_target, headers=headers, timeout=12.0)
                html = fetch.text

        # 1. Plain HLS pattern: 'hls': 'https://...'
        hls_match = re.search(r'[\'"]hls[\'"]\s*:\s*[\'"](https?://[^\'"]+)[\'"]', html)
        if hls_match:
            hls_url = hls_match.group(1).strip()
            hops.append(make_hop(
                url=hls_url,
                status_code=200,
                redirect_type="voe_hls_stream",
                extra_details="Found unencrypted Voe HLS stream",
                hop_number=len(hops) + 1,
            ))
            return hls_url, hops

        # 2. JSON script payload
        script_match = re.findall(r'<script\s+type=["\']application/json["\']>(.*?)</script>', html, re.DOTALL)
        for block in script_match:
            clean_block = block.strip().strip('"')
            if "hls" in clean_block or "http" in clean_block:
                try:
                    data = json.loads(clean_block)
                    if isinstance(data, dict) and (data.get("source") or data.get("hls")):
                        stream_url = data.get("source") or data.get("hls")
                        return stream_url, hops
                except Exception as parse_err:
                    logger.debug("Voe JSON block parsing failed: %s", parse_err)


        # 3. Direct .m3u8 pattern
        direct_m3u8 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        if direct_m3u8:
            stream_url = direct_m3u8.group(0)
            hops.append(make_hop(
                url=stream_url,
                status_code=200,
                redirect_type="voe_m3u8_fallback",
                extra_details="Captured direct Voe m3u8 stream",
                hop_number=len(hops) + 1,
            ))
            return stream_url, hops

        return None

    async def _resolve_filemoon(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": url,
        }

        fetch = await request_capped(client, url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=url,
            status_code=fetch.status_code,
            redirect_type="filemoon_embed",
            extra_details="Fetched Filemoon embed",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        unpacked = unpack_packer(html) if detect_packed(html) else ""
        content = html + "\n" + unpacked

        m3u8_match = re.search(r'sources:\s*\[\{[^}]*file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', content)
        if not m3u8_match:
            m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)

        if m3u8_match:
            stream_url = m3u8_match.group(1).strip()
            hops.append(make_hop(
                url=stream_url,
                status_code=200,
                redirect_type="filemoon_hls_stream",
                extra_details="Extracted Filemoon HLS manifest from unpacked JS",
                hop_number=len(hops) + 1,
            ))
            return stream_url, hops

        return None

    async def _resolve_kwik(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": "https://animepahe.com/",
        }

        fetch = await request_capped(client, url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=url,
            status_code=fetch.status_code,
            redirect_type="kwik_page",
            extra_details="Fetched Kwik player embed",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        # Kwik uses a form POST with token and action URL
        action_match = re.search(r'action="([^"]+)"', html)
        token_match = re.search(r'name="_token"\s+value="([^"]+)"', html)

        if action_match and token_match:
            post_url = action_match.group(1).strip()
            token = token_match.group(1).strip()
            post_headers = {
                "User-Agent": headers["User-Agent"],
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded",
            }
            hops.append(make_hop(
                url=post_url,
                status_code=200,
                redirect_type="kwik_post_token",
                extra_details="Found Kwik authentication form and token",
                hop_number=len(hops) + 1,
            ))
            return post_url, hops

        # Check for unpacked scripts
        if detect_packed(html):
            unpacked = unpack_packer(html)
            direct_match = re.search(r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*', unpacked)
            if direct_match:
                stream_url = direct_match.group(0)
                return stream_url, hops

        return None

    async def _resolve_vidhide(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        embed_url = url
        if "/v/" in url:
            embed_url = url.replace("/v/", "/e/")
        elif "/d/" in url:
            embed_url = url.replace("/d/", "/e/")

        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": embed_url,
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="vidhide_embed",
            extra_details="Fetched VidHide player container",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        unpacked = unpack_packer(html) if detect_packed(html) else ""
        content = html + "\n" + unpacked

        # 1. Links object: links = {hls4: '...', hls3: '...', hls: '...'}
        links_match = re.search(r'\blinks\s*=\s*\{([\s\S]*?)\}\s*;', content)
        if links_match:
            block = links_match.group(1)
            for key in ("hls4", "hls3", "hls2", "hls"):
                m = re.search(rf'["\']?{key}["\']?\s*:\s*["\']([^"\']+)["\']', block, re.I)
                if m:
                    cand = m.group(1).replace(r"\/", "/").strip()
                    if cand.startswith("//"):
                        cand = "https:" + cand
                    elif not cand.startswith("http"):
                        cand = urllib.parse.urljoin(embed_url, cand)
                    hops.append(make_hop(
                        url=cand,
                        status_code=200,
                        redirect_type="vidhide_hls_stream",
                        extra_details=f"Extracted VidHide stream via {key}",
                        hop_number=len(hops) + 1,
                    ))
                    return cand, hops

        # 2. General Master HLS stream in script
        m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
        if m3u8_match:
            stream_url = m3u8_match.group(1).strip()
            hops.append(make_hop(
                url=stream_url,
                status_code=200,
                redirect_type="vidhide_m3u8_stream",
                extra_details="Extracted VidHide HLS stream",
                hop_number=len(hops) + 1,
            ))
            return stream_url, hops

        return None

    async def _resolve_luluvdo(
        self, url: str, client: Any, context: ResolutionContext, hops: List[HopInfo]
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        embed_url = url
        if "/d/" in url:
            embed_url = url.replace("/d/", "/e/")

        headers = {
            "User-Agent": default_headers().get("User-Agent", ""),
            "Referer": embed_url,
        }

        fetch = await request_capped(client, embed_url, headers=headers, timeout=12.0)
        hops.append(make_hop(
            url=embed_url,
            status_code=fetch.status_code,
            redirect_type="luluvdo_embed",
            extra_details="Fetched LuluVdo player container",
            hop_number=len(hops) + 1,
        ))

        html = fetch.text
        if not html:
            return None

        unpacked = unpack_packer(html) if detect_packed(html) else ""
        content = html + "\n" + unpacked

        m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', content)
        if m3u8_match:
            stream_url = m3u8_match.group(1).strip()
            hops.append(make_hop(
                url=stream_url,
                status_code=200,
                redirect_type="luluvdo_hls_stream",
                extra_details="Extracted LuluVdo HLS stream from unpacked JS",
                hop_number=len(hops) + 1,
            ))
            return stream_url, hops

        return None

