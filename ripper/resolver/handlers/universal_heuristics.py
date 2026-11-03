"""
Universal Heuristics Handler.
Handles HTTP 3xx Location redirects, HTML Meta-Refresh, JS window.location,
and Base64 query parameter unwrapping for unshortening any generic link.
"""
from __future__ import annotations

import base64
import html as html_lib
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ...models import HopInfo

logger = logging.getLogger(__name__)


class UniversalHeuristicsHandler(BaseResolverHandler):
    name = "universal_heuristics"
    priority = 90  # Fallback priority when no specialized site handler matches

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        return True  # Catch-all universal fallback

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        try:
            # 1. Inspect query parameters for destination URLs first
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            for param_key in ("url", "dest", "target", "link", "goto", "redirect", "r", "u", "to"):
                if param_key in qs:
                    raw_val = qs[param_key][0]
                    if raw_val.startswith("http"):
                        hops.append(make_hop(url=raw_val, status_code=200, redirect_type="query_param", extra_details=f"Unwrapped ?{param_key}="))
                        return raw_val, hops
                    # Try Base64
                    try:
                        decoded = base64.b64decode(raw_val).decode("utf-8", errors="ignore")
                        if decoded.startswith("http"):
                            hops.append(make_hop(url=decoded, status_code=200, redirect_type="base64_query", extra_details="Decoded Base64 query parameter"))
                            return decoded, hops
                    except Exception as exc:
                        logger.debug("Query param base64 decode attempt failed: %s", exc)

            # 2. Perform HTTP request
            resp = await client.get(url, headers=context.extra_headers, timeout=context.timeout)
            status = resp.status_code
            text = resp.text

            hops.append(make_hop(url=url, status_code=status, redirect_type="http_response", extra_details=f"HTTP response {status}"))

            # Check Location header on redirects
            if status in (301, 302, 303, 307, 308) and "location" in resp.headers:
                loc = resp.headers["location"].strip()
                full_loc = urllib.parse.urljoin(url, loc)
                hops.append(make_hop(url=full_loc, status_code=status, redirect_type="http_3xx", extra_details=f"3xx Location redirect to {full_loc}"))
                return full_loc, hops

            # 3. HTML Meta-Refresh tag: <meta http-equiv="refresh" content="0;url=...">
            match_meta = re.search(r'<meta[^>]+http-equiv=["\x27]?refresh["\x27]?[^>]+content=["\x27]?\d+;\s*url=([^"\x27>]+)', text, re.IGNORECASE)
            if match_meta:
                next_url = html_lib.unescape(match_meta.group(1).strip())
                full_meta = urllib.parse.urljoin(url, next_url)
                hops.append(make_hop(url=full_meta, status_code=status, redirect_type="meta_refresh", extra_details="HTML Meta-Refresh tag detected"))
                return full_meta, hops

            # 4. JavaScript window.location or location.href redirects
            match_js = re.search(r'(?:window\.)?location(?:\.href)?\s*=\s*["\x27](https?://[^"\x27]+)["\x27]', text)
            if match_js:
                next_url = match_js.group(1).strip()
                hops.append(make_hop(url=next_url, status_code=status, redirect_type="js_redirect", extra_details="JavaScript window.location redirect"))
                return next_url, hops

            # 5. Universal embedded video stream extraction (JWPlayer, VideoJS, bare .m3u8, .mp4)
            from ..core import extract_embedded_media_stream
            media_stream = extract_embedded_media_stream(text, base_url=url)
            if media_stream and media_stream != url:
                hops.append(make_hop(url=media_stream, status_code=status, redirect_type="embedded_media_stream", extra_details="Extracted direct media stream from page"))
                return media_stream, hops

            # 6. Embedded iframe player extraction (e.g. <iframe src="...player...">)
            match_iframe = re.search(r'<iframe[^>]+src=["\x27](https?://[^"\x27]+)["\x27]', text, re.I)
            if match_iframe:
                iframe_url = html_lib.unescape(match_iframe.group(1).strip())
                if iframe_url != url and not any(bad in iframe_url.lower() for bad in ("google", "facebook", "twitter", "analytics", "ads")):
                    hops.append(make_hop(url=iframe_url, status_code=status, redirect_type="iframe_embed", extra_details="Extracted embedded player iframe"))
                    return iframe_url, hops

        except Exception as exc:
            logger.debug("Universal heuristics extraction failed for %s: %s", url, exc)
            hops.append(make_hop(url=url, status_code=0, redirect_type="heuristic_error", extra_details=str(exc)))

        return None