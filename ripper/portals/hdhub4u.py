"""
HDHub4u & HubCloud / GadgetsWeb Modular Resolver.
Implements the 5-step Rot13/Base64 client-side token decrypter.
"""

from __future__ import annotations

import base64
import json
import re
from typing import List, Optional
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get


def decrypt_hdhub4u_gadgetsweb_token(token: str) -> Optional[str]:
    """
    Decodes the obfuscated token from GadgetsWeb / HDHub4u into a direct HubCloud URL.
    Flow: Base64 -> Base64 -> Rot13 -> Base64 -> JSON -> Base64 = HubCloud URL!
    """
    try:
        s1 = base64.b64decode(token).decode("utf-8")
        s2 = base64.b64decode(s1).decode("utf-8")
        s3 = "".join(
            chr((ord(c) - ord('a' if c.islower() else 'A') + 13) % 26 + ord('a' if c.islower() else 'A'))
            if c.isalpha() else c for c in s2
        )
        padded = s3 + "=" * ((4 - len(s3) % 4) % 4)
        s4 = base64.b64decode(padded).decode("utf-8")
        data = json.loads(s4)
        hubcloud_b64 = data.get("o")
        if hubcloud_b64:
            return base64.b64decode(hubcloud_b64).decode("utf-8")
    except Exception:
        pass
    return None


class HDHub4uPortal(BasePortalResolver):
    @property
    def name(self) -> str:
        return "HDHub4u / HubCloud"

    @property
    def supported_domains(self) -> List[str]:
        return ["hdhub4u", "hubcloud", "hubcdn", "gadgetsweb", "vcloud"]

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        results: List[PortalStreamResult] = []
        try:
            # 1. If URL is a GadgetsWeb token landing page, decrypt token directly
            if "gadgetsweb" in url or "?id=" in url:
                resp = await client.get(url, timeout=5.0)
                m = re.search(r"s\('o','([^']+)'", resp.text)
                if m:
                    hub_url = decrypt_hdhub4u_gadgetsweb_token(m.group(1))
                    if hub_url:
                        url = hub_url

            # 2. If URL is a HubCloud page, extract direct download CDN links
            if "hubcloud" in url or "hubcdn" in url or "vcloud" in url:
                r = await client.get(url, timeout=5.0)
                # Search for direct download anchor tags
                for m_link in re.finditer(r'href="([^"]+)"[^>]*>([^<]*?(?:Download|Fast\s*Cloud|PixelDrain|Direct)[^<]*?)<', r.text, re.IGNORECASE):
                    link = m_link.group(1)
                    label = m_link.group(2).strip()
                    if link.startswith("http"):
                        results.append(PortalStreamResult(
                            direct_url=link,
                            filename=label,
                            portal_name=self.name,
                        ))
        except Exception:
            pass
        return results
