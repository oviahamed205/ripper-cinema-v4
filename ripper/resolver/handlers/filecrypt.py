"""FileCrypt Container & DLC Decryptor Handler (filecrypt.co, filecrypt.cc, filecrypt.to).

Unpacks protected file folders from FileCrypt containers, supporting direct
container link extraction and DLC payload decryption via dcrypt.it API.
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import Any, List, Optional, Tuple

from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import _clean_extracted_url, _is_followable_http_url, request_capped
from ...models import HopInfo

logger = logging.getLogger(__name__)

FILECRYPT_DOMAINS = ("filecrypt.co", "filecrypt.cc", "filecrypt.to")


class FileCryptHandler(BaseResolverHandler):
    name = "filecrypt"
    priority = 22

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        return any(d in low for d in FILECRYPT_DOMAINS)

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": url,
                **(context.extra_headers or {}),
            }
            page = await request_capped(client, url, headers=headers, timeout=context.timeout)
            if not page.text:
                return None

            soup = BeautifulSoup(page.text, "html.parser")

            # 1. Look for direct links table or container buttons
            extracted_links: List[str] = []
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if (
                    href.startswith("http")
                    and not any(d in href for d in FILECRYPT_DOMAINS)
                    and _is_followable_http_url(href)
                ):
                    extracted_links.append(_clean_extracted_url(href))

            if extracted_links:
                chosen_link = extracted_links[0]
                hops.append(
                    make_hop(
                        url=chosen_link,
                        status_code=200,
                        redirect_type="filecrypt_table_direct",
                        extra_details=f"Extracted direct link from FileCrypt container ({len(extracted_links)} links discovered)",
                        hop_number=len(context.hops) + 1,
                    )
                )
                return chosen_link, hops

            # 2. Check for DLC container download button or base64 data
            dlc_id_match = re.search(r'/DLC/([a-zA-Z0-9_-]+)\.dlc', page.text)
            if dlc_id_match:
                dlc_url = urllib.parse.urljoin(url, f"/DLC/{dlc_id_match.group(1)}.dlc")
                dlc_resp = await client.get(dlc_url, headers=headers, timeout=context.timeout)
                if dlc_resp.status_code == 200 and dlc_resp.text:
                    # Query dcrypt.it API to unpack DLC payload
                    decrypt_url = "http://dcrypt.it/decrypt/paste"
                    api_headers = {
                        "User-Agent": headers["User-Agent"],
                        "Accept": "application/json, text/javascript, */*",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": "http://dcrypt.it/",
                    }
                    api_resp = await client.post(
                        decrypt_url,
                        data={"content": dlc_resp.text},
                        headers=api_headers,
                        timeout=context.timeout,
                    )
                    if api_resp.status_code == 200:
                        data = api_resp.json() if hasattr(api_resp, "json") else {}
                        unpacked_links = (data.get("success") or {}).get("links") or []
                        if unpacked_links and isinstance(unpacked_links, list):
                            first_link = str(unpacked_links[0])
                            hops.append(
                                make_hop(
                                    url=first_link,
                                    status_code=200,
                                    redirect_type="filecrypt_dcrypt_dlc",
                                    extra_details=f"Decrypted {len(unpacked_links)} links from FileCrypt DLC via dcrypt.it",
                                    hop_number=len(context.hops) + 1,
                                )
                            )
                            return first_link, hops

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("FileCrypt container resolution failed: %s", exc)

        return None
