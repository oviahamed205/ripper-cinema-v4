"""
GDToT / KatDrive / DriveFire / HubDrive / Kolop Handler.
Extracts direct Google Drive links via /ajax.php?ajax=download session handshakes and tokenized streams.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ...models import HopInfo, ServerMirror

logger = logging.getLogger(__name__)

GDTOT_DOMAINS = (
    "gdtot.to", "gdtot.pro", "gdtot.me", "gdtot.sbs", "gdtot.life", "gdtot.cfd",
    "katdrive.net", "katdrive.org", "drivefire.co", "kolop.icu", "hubdrive.me",
    "hubdrive.cc", "gdflix.top", "gdflix.info", "appdrive.info",
    "appdrive.in", "jiodrive.xyz", "drivehub.ws", "driveseed.org",
    "sharer.pw",
)



class GDToTHandler(BaseResolverHandler):
    name = "gdtot"
    priority = 25

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        if any(d in low for d in GDTOT_DOMAINS):
            return True
        if html and any(sig in html.lower() for sig in ("gdtot", "katdrive", "drivefire", "appdrive")):
            return True
        return False

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        try:
            crypt_token = (
                context.cookies.get("crypt")
                or os.environ.get("KATDRIVE_CRYPT")
                or os.environ.get("CRYPT")
                or os.environ.get("HUBDRIVE_CRYPT")
                or os.environ.get("DRIVEFIRE_CRYPT")
                or os.environ.get("KOLOP_CRYPT")
            )
            req_headers = dict(context.extra_headers)
            if crypt_token and "Cookie" not in req_headers:
                req_headers["Cookie"] = f"crypt={crypt_token}"

            resp = await client.get(url, headers=req_headers, timeout=context.timeout)
            html = getattr(resp, "text", "")
            status = getattr(resp, "status_code", 200)

            hops.append(make_hop(
                url=url,
                status_code=status,
                redirect_type="gdtot_landing",
                extra_details=f"GDToT/Drive gateway landing fetched (status {status})",
            ))

            crypt_match = re.search(r'name=["\x27]crypt["\x27]\s+value=["\x27]([^"\x27]+)["\x27]', html)
            if crypt_match:
                crypt_token = crypt_match.group(1)
                context.cookies["crypt"] = crypt_token
                hops.append(make_hop(url=url, status_code=status, redirect_type="gdtot_crypt", extra_details="Captured crypt token"))

            # Sharer.pw direct bridge
            if "sharer.pw" in url.lower():
                token_match = re.search(r"_token\s*=\s*['\"]([^'\"]+)['\"]", html)
                if token_match:
                    csrf_token = token_match.group(1)
                    parsed_sh = urllib.parse.urlparse(url)
                    sh_file_id = parsed_sh.path.rstrip("/").split("/")[-1]
                    dl_endpoint = f"{parsed_sh.scheme}://{parsed_sh.netloc}/file/{sh_file_id}/dl"
                    sh_headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": url,
                    }
                    try:
                        sh_resp = await client.post(
                            dl_endpoint,
                            data={"_token": csrf_token, "nl": 1},
                            headers=sh_headers,
                            timeout=context.timeout,
                        )
                        if getattr(sh_resp, "status_code", 0) == 200:
                            sh_data = sh_resp.json() if hasattr(sh_resp, "json") else {}
                            drive_link = sh_data.get("url") or (sh_data if isinstance(sh_data, str) and sh_data.startswith("http") else None)
                            if drive_link:
                                hops.append(make_hop(
                                    url=drive_link,
                                    status_code=200,
                                    redirect_type="sharerpw_drive_bridge",
                                    extra_details=f"Extracted Sharer.pw Google Drive target: {sh_file_id}",
                                    hop_number=len(context.hops) + 1,
                                ))
                                return drive_link, hops
                    except Exception as exc:
                        logger.debug("Sharer.pw AJAX request failed: %s", exc)

            parsed = urllib.parse.urlparse(url)
            file_id = parsed.path.rstrip("/").split("/")[-1]
            if file_id and (len(file_id) >= 6 or file_id.isdigit()):
                ajax_url = f"{parsed.scheme}://{parsed.netloc}/ajax.php?ajax=download"
                ajax_headers = dict(req_headers)
                ajax_headers.update({
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": url,
                    "Origin": f"{parsed.scheme}://{parsed.netloc}",
                })
                if crypt_token:
                    ajax_headers["Cookie"] = f"crypt={crypt_token}"

                try:
                    ajax_resp = await client.post(
                        ajax_url,
                        data={"id": file_id},
                        headers=ajax_headers,
                        timeout=context.timeout,
                    )
                    if getattr(ajax_resp, "status_code", 0) == 200:
                        try:
                            data = ajax_resp.json()
                            if isinstance(data, dict) and "file" in data:
                                file_str = str(data["file"])
                                gd_match = re.search(r"gd=([a-zA-Z0-9_\-]+)", file_str)
                                if gd_match:
                                    gdrive_url = f"https://drive.google.com/open?id={gd_match.group(1)}"
                                    hops.append(make_hop(
                                        url=gdrive_url,
                                        status_code=200,
                                        redirect_type="gdtot_ajax_gd",
                                        extra_details=f"Extracted Google Drive ID: {gd_match.group(1)}",
                                    ))
                                    return gdrive_url, hops

                                if "drive.google.com" in file_str or file_str.startswith("http"):
                                    hops.append(make_hop(
                                        url=file_str,
                                        status_code=200,
                                        redirect_type="gdtot_ajax_direct",
                                        extra_details="Extracted direct download stream from AJAX",
                                    ))
                                    return file_str, hops

                                decoded_id = file_str.rsplit("/", 1)[-1]
                                if len(decoded_id) > 10:
                                    gdrive_url = f"https://drive.google.com/file/d/{decoded_id}"
                                    hops.append(make_hop(
                                        url=gdrive_url,
                                        status_code=200,
                                        redirect_type="gdtot_ajax_file_id",
                                        extra_details="Constructed Drive URL from file ID",
                                    ))
                                    return gdrive_url, hops
                        except Exception as exc:
                            logger.debug("GDToT JSON parsing failed: %s", exc)
                except Exception as exc:
                    logger.debug("GDToT AJAX post failed: %s", exc)


            soup = BeautifulSoup(html, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in ("instant download", "drive download", "direct download", "download file")):
                    full = urllib.parse.urljoin(url, href)
                    hops.append(make_hop(url=full, status_code=status, redirect_type="gdtot_button", extra_details=f"Found: {text}"))
                    return full, hops

            for form in soup.find_all("form"):
                action = form.get("action", "")
                if action and action.startswith("http"):
                    hops.append(make_hop(url=action, status_code=status, redirect_type="gdtot_form", extra_details="Extracted form action"))
                    return action, hops

        except Exception as exc:
            hops.append(make_hop(url=url, status_code=0, redirect_type="gdtot_error", extra_details=f"GDToT error: {exc}"))

        return None