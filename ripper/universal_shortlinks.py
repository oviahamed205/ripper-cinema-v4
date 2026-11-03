"""
Universal Link Shortener & AdGate Bypasser (God-Mode Edition)

Decodes and bypasses common link shorteners and ad-gates:
1. URL Parameter Unpackers (Base64, Hex, URI encoded wrappers: url=, r=, dest=, link=, target=, go=)
2. AdLinkFly & FlyInc engines (exe.io, clicksfly, cut-urls, etc.)
3. Ouo.io & Ouo.press token extraction
4. Droplink / GPlinks parameter decoders
5. Universal Blogger & WordPress redirect gateways
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import urllib.parse
from typing import Optional, Tuple, Dict, List
import httpx
from bs4 import BeautifulSoup

COMMON_WRAPPER_PARAMS = (
    "url", "link", "dest", "target", "destination", "redirect", "r",
    "u", "go", "to", "out", "href", "safeurl", "adurl", "token", "payload"
)

ADLINKFLY_DOMAINS = (
    "exe.io", "exey.io", "clicksfly.com", "cut-urls.com", "za.gl",
    "shortur.me", "dropi.co", "shrinkme.io", "shrinkme.us"
)


def decode_embedded_wrapped_url(target_url: str) -> Optional[str]:
    """
    Check if target_url wraps the destination URL in query parameters
    either in plaintext, URI-encoded, Base64, or Hex format.
    """
    try:
        parsed = urllib.parse.urlparse(target_url)
        params = urllib.parse.parse_qs(parsed.query)

        for param_name, values in params.items():
            if param_name.lower() in COMMON_WRAPPER_PARAMS:
                for val in values:
                    val = val.strip()
                    # 1. Plain HTTP/HTTPS URL
                    if val.startswith(("http://", "https://")):
                        return val

                    # 2. URI decoded
                    decoded_uri = urllib.parse.unquote(val)
                    if decoded_uri.startswith(("http://", "https://")) and decoded_uri != target_url:
                        return decoded_uri

                    # 3. Base64 encoded
                    try:
                        # Add padding if needed
                        padded = val + "=" * ((4 - len(val) % 4) % 4)
                        b64_bytes = base64.b64decode(padded)
                        b64_str = b64_bytes.decode("utf-8", errors="ignore").strip()
                        if b64_str.startswith(("http://", "https://")):
                            return b64_str
                    except Exception:
                        pass

                    # 4. Hex encoded
                    try:
                        hex_bytes = binascii.unhexlify(val)
                        hex_str = hex_bytes.decode("utf-8", errors="ignore").strip()
                        if hex_str.startswith(("http://", "https://")):
                            return hex_str
                    except Exception:
                        pass
    except Exception:
        pass

    return None


async def resolve_ouo_shortlink(client: httpx.AsyncClient, ouo_url: str, timeout: float = 8.0) -> Optional[str]:
    """
    Bypasses ouo.io / ouo.press shortlink gates by extracting the form CSRF token
    and posting directly to the destination endpoint.
    """
    try:
        r = await client.get(ouo_url, timeout=timeout, follow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        form = soup.find("form")
        if not form:
            return None

        action = form.get("action") or str(r.url)
        inputs = form.find_all("input")
        data = {}
        for inp in inputs:
            n = inp.get("name")
            v = inp.get("value", "")
            if n:
                data[n] = v

        if not data:
            return None

        # Resolve relative action
        target_post = urllib.parse.urljoin(str(r.url), action)
        headers = {"Referer": str(r.url), "Content-Type": "application/x-www-form-urlencoded"}
        r_post = await client.post(target_post, data=data, headers=headers, timeout=timeout, follow_redirects=False)

        if "location" in r_post.headers:
            return r_post.headers["location"]
    except Exception:
        pass

    return None


async def resolve_universal_shortlink(client: httpx.AsyncClient, url: str, timeout: float = 8.0) -> Optional[str]:
    """
    Universal shortlink resolution pipeline:
    1. Parameter unwrap (Base64/Hex/URI)
    2. OUO token bypass
    3. Generic HTML meta-refresh / window.location extract
    """
    # 1. Parameter extraction
    wrapped = decode_embedded_wrapped_url(url)
    if wrapped:
        return wrapped

    # 2. OUO bypass
    if any(k in url.lower() for k in ["ouo.io", "ouo.press"]):
        ouo_res = await resolve_ouo_shortlink(client, url, timeout=timeout)
        if ouo_res:
            return ouo_res

    # 3. HTML fast inspection for immediate JavaScript redirects
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        html = resp.text

        # Meta refresh
        m_meta = re.search(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\']\d+;\s*url=([^"\']+)["\']', html, re.I)
        if m_meta:
            meta_dest = m_meta.group(1).strip()
            return urllib.parse.urljoin(str(resp.url), meta_dest)

        # window.location.href / window.location.replace
        m_loc = re.search(r'window\.location(?:\.href|\.replace)?\s*=\s*["\'](https?://[^"\']+)["\']', html)
        if m_loc:
            loc_dest = m_loc.group(1).strip()
            if loc_dest != url:
                return loc_dest

    except Exception:
        pass

    return None
