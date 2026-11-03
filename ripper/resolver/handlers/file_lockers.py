"""
Cloud File Lockers Handler (Pixeldrain, GoFile, MediaFire, KrakenFiles, 1Fichier).
Extracts direct download streams without human captcha or artificial wait times.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


from ..base import BaseResolverHandler, ResolutionContext, make_hop
from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    coerce_timeout,
    request_capped,
)
from ...models import HopInfo


GOFILE_WEBSITE_TOKEN = os.environ.get("UNSHORTEN_GOFILE_WT", "4fd6sg89d7s6")

LOCKER_DOMAINS = (
    "pixeldrain.com", "pixeldrain.dev", "gofile.io", "mediafire.com",
    "1fichier.com", "send.cm", "racaty.net", "racaty.io", "krakenfiles.com", "filechan.org",
    "streamtape.com", "streamtape.to", "streamtape.xyz", "streamtape.net",
    "skydrop.sbs", "skydrop.me", "skydrop.link",
    "solidfiles.com", "sfile.mobi", "antfiles.com", "mdisk.me",
    "watchsb.com", "streamsb.net", "sbembed.com", "sbvideo.net", "playersb.com",
    "fembed.com", "fembed-hd.com", "femax20.com", "feurl.com", "megaup.net",
)



class FileLockersHandler(BaseResolverHandler):
    name = "file_lockers"
    priority = 15

    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        low = url.lower()
        return any(d in low for d in LOCKER_DOMAINS)

    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        hops: List[HopInfo] = []
        low = url.lower()

        # 1. PixelDrain API Conversion
        if "pixeldrain.com" in low or "pixeldrain.dev" in low:
            m = re.search(r"pixeldrain\.(?:com|dev)/(?:u|l)/([a-zA-Z0-9_-]+)", url)
            if m:
                file_id = m.group(1).strip("/")
                direct_url = f"https://pixeldrain.com/api/file/{file_id}?download"
                hops.append(make_hop(
                    url=direct_url,
                    status_code=200,
                    redirect_type="pixeldrain_api",
                    extra_details=f"Direct Pixeldrain stream: {file_id}",
                    hop_number=len(context.hops) + 1,
                ))
                return direct_url, hops

        # 2. GoFile Direct API Handshake
        if "gofile.io" in low:
            direct_gofile = await self._resolve_gofile(url, client, context, hops)
            if direct_gofile:
                return direct_gofile, hops
            # If API fails, return link as-is with hop
            hops.append(make_hop(
                url=url,
                status_code=200,
                redirect_type="gofile_link",
                extra_details="GoFile locker detected",
                hop_number=len(context.hops) + 1,
            ))
            return url, hops

        # 3. MediaFire Direct Extraction
        if "mediafire.com" in low:
            direct_mf = await self._resolve_mediafire(url, client, context, hops)
            if direct_mf:
                return direct_mf, hops

        # 4. KrakenFiles Direct Button/API Extraction
        if "krakenfiles.com" in low:
            direct_kf = await self._resolve_krakenfiles(url, client, context, hops)
            if direct_kf:
                return direct_kf, hops

        # 5. Streamtape Direct Video Stream Extraction
        if any(d in low for d in ("streamtape.com", "streamtape.to", "streamtape.xyz", "streamtape.net")):
            direct_st = await self._resolve_streamtape(url, client, context, hops)
            if direct_st:
                return direct_st, hops

        # 6. Send.cm Direct Download Extraction
        if "send.cm" in low:
            direct_send = await self._resolve_sendcm(url, client, context, hops)
            if direct_send:
                return direct_send, hops

        # 7. Skydrop Cloud Service Extraction
        if any(d in low for d in ("skydrop.sbs", "skydrop.me", "skydrop.link")):
            direct_sky = await self._resolve_skydrop(url, client, context, hops)
            if direct_sky:
                return direct_sky, hops

        # 8. Racaty Direct Form Extraction
        if "racaty.net" in low or "racaty.io" in low:
            direct_racaty = await self._resolve_racaty(url, client, context, hops)
            if direct_racaty:
                return direct_racaty, hops

        # 9. SolidFiles JSON Options Extraction
        if "solidfiles.com" in low:
            direct_sf = await self._resolve_solidfiles(url, client, context, hops)
            if direct_sf:
                return direct_sf, hops

        # 10. SFile Mobi Direct Download Extraction
        if "sfile.mobi" in low:
            direct_sfile = await self._resolve_sfile(url, client, context, hops)
            if direct_sfile:
                return direct_sfile, hops

        # 11. StreamSB Multi-Mirror Video Extractor
        if any(d in low for d in ("watchsb.com", "streamsb.net", "sbembed.com", "sbvideo.net", "playersb.com")):
            direct_sb = await self._resolve_streamsb(url, client, context, hops)
            if direct_sb:
                return direct_sb, hops

        # 12. Fembed Source API Extractor
        if any(d in low for d in ("fembed.com", "fembed-hd.com", "femax20.com", "feurl.com")):
            direct_fe = await self._resolve_fembed(url, client, context, hops)
            if direct_fe:
                return direct_fe, hops

        # 13. AntFiles Direct CDN Extractor
        if "antfiles.com" in low:
            direct_ant = await self._resolve_antfiles(url, client, context, hops)
            if direct_ant:
                return direct_ant, hops

        # 14. MDisk CDN Direct Converter
        if "mdisk.me" in low:
            direct_mdisk = await self._resolve_mdisk(url, client, context, hops)
            if direct_mdisk:
                return direct_mdisk, hops

        # 15. MegaUp Direct Extraction
        if "megaup.net" in low:
            direct_megaup = await self._resolve_megaup(url, client, context, hops)
            if direct_megaup:
                return direct_megaup, hops

        return None


    async def _resolve_gofile(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Handshake with GoFile official API to create guest session and resolve download link."""
        try:
            if "/d/" not in url:
                return None
            content_id = url.split("/d/")[-1].split("?")[0].strip("/")
            if not content_id:
                return None

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            # Step A: Create Guest Account Token
            account_resp = await client.post(
                "https://api.gofile.io/accounts",
                headers=headers,
                timeout=context.timeout,
            )
            payload = account_resp.json() if hasattr(account_resp, "json") else {}
            token = (payload.get("data") or {}).get("token", "")
            if not token:
                return None

            # Step B: Fetch Folder Contents
            listing_resp = await client.get(
                f"https://api.gofile.io/contents/{content_id}?wt={GOFILE_WEBSITE_TOKEN}",
                headers={**headers, "Authorization": f"Bearer {token}"},
                timeout=context.timeout,
            )
            listing = listing_resp.json() if hasattr(listing_resp, "json") else {}
            data = listing.get("data") or {}
            children = data.get("children") or {}
            for child_id, child_info in children.items():
                if isinstance(child_info, dict):
                    link = child_info.get("link")
                    if link and _is_followable_http_url(str(link)):
                        direct = str(link)
                        hops.append(make_hop(
                            url=direct,
                            status_code=200,
                            redirect_type="gofile_api_direct",
                            extra_details=f"GoFile direct CDN stream resolved: {child_info.get('name', '')}",
                            hop_number=len(context.hops) + 1,
                        ))
                        return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            hops.append(make_hop(
                url=url,
                status_code=0,
                redirect_type="gofile_api_error",
                extra_details=f"GoFile API handshake error: {exc}",
                hop_number=len(context.hops) + 1,
            ))
        return None

    async def _resolve_mediafire(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download CDN anchor from MediaFire HTML."""
        try:
            page = await request_capped(client, url, headers=context.extra_headers, timeout=context.timeout)
            if page.text:
                m = re.search(r'href=["\x27](https?://download\d+\.mediafire\.com/[^"\x27]+)["\x27]', page.text)
                if m:
                    direct = _clean_extracted_url(m.group(1))
                    hops.append(make_hop(
                        url=direct,
                        status_code=200,
                        redirect_type="mediafire_direct",
                        extra_details="Direct MediaFire CDN download link extracted",
                        hop_number=len(context.hops) + 1,
                    ))
                    return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Mediafire resolution failed: %s", exc)
        return None

    async def _resolve_krakenfiles(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download stream from KrakenFiles via API handshake or anchor fallback."""
        try:
            page = await request_capped(client, url, headers=context.extra_headers, timeout=context.timeout)
            if not page.text:
                return None

            soup = BeautifulSoup(page.text, "html.parser")
            token_input = soup.find("input", id="dl-token")
            hash_div = soup.find("div", attrs={"data-file-hash": True})

            if token_input and hash_div and token_input.get("value") and hash_div.get("data-file-hash"):
                token = token_input["value"]
                dl_hash = hash_div["data-file-hash"]
                api_url = f"https://krakenfiles.com/download/{dl_hash}"
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Referer": url,
                    "Origin": "https://krakenfiles.com",
                }
                api_resp = await client.post(
                    api_url,
                    data={"token": token},
                    headers=headers,
                    timeout=context.timeout,
                )
                if api_resp.status_code == 200:
                    data = api_resp.json() if hasattr(api_resp, "json") else {}
                    dl_url = data.get("url")
                    if dl_url and _is_followable_http_url(str(dl_url)):
                        direct = str(dl_url).replace(" ", "%20")
                        hops.append(make_hop(
                            url=direct,
                            status_code=200,
                            redirect_type="krakenfiles_api_direct",
                            extra_details="KrakenFiles high-speed CDN stream resolved via API",
                            hop_number=len(context.hops) + 1,
                        ))
                        return direct

            # Fallback: Scrape direct download button/anchor
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if "/download/" in href or "krakenfiles.com/dl/" in href:
                    direct = urllib.parse.urljoin(url, href)
                    hops.append(make_hop(
                        url=direct,
                        status_code=200,
                        redirect_type="krakenfiles_direct",
                        extra_details="KrakenFiles direct download resolved via HTML anchor",
                        hop_number=len(context.hops) + 1,
                    ))
                    return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("KrakenFiles resolution failed: %s", exc)
        return None

    async def _resolve_streamtape(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct streaming video link from Streamtape (/e/ or /v/ URL)."""
        try:
            norm_url = url.replace("/e/", "/v/")
            page = await request_capped(client, norm_url, headers=context.extra_headers, timeout=context.timeout)
            if not page.text:
                return None

            norobot_match = re.search(
                r"document\.getElementById\(['\"]norobotlink['\"]\)\.innerHTML\s*=\s*([^;]+);",
                page.text,
            )
            token_match = None
            if norobot_match:
                token_match = re.search(r"token=([^&'\"]+)", norobot_match.group(1))

            if not token_match:
                token_match = re.search(r"token=([a-zA-Z0-9_-]+)", page.text)

            link_div_match = re.search(
                r'id=["\']ideoooolink["\'][^>]*>([^<]+)<',
                page.text,
            )
            if not link_div_match:
                # Alternative regex for robotlink/streamtape text
                link_div_match = re.search(r'//([a-zA-Z0-9.-]+/get_video\?[^"\'\s<>&]+)', page.text)

            if token_match and link_div_match:
                token = token_match.group(1)
                stream_part = link_div_match.group(1).strip()
                if not stream_part.startswith("http"):
                    if not stream_part.startswith("/"):
                        stream_part = "/" + stream_part
                    if not stream_part.startswith("//"):
                        stream_part = "/" + stream_part
                    direct = f"https:{stream_part}&token={token}&dl=1"
                else:
                    direct = f"{stream_part}&token={token}&dl=1"

                hops.append(make_hop(
                    url=direct,
                    status_code=200,
                    redirect_type="streamtape_direct_stream",
                    extra_details="Streamtape direct video stream resolved",
                    hop_number=len(context.hops) + 1,
                ))
                return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Streamtape resolution failed: %s", exc)
        return None

    async def _resolve_sendcm(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download stream from Send.cm via download2 form submission."""
        try:
            page = await request_capped(client, url, headers=context.extra_headers, timeout=context.timeout)
            if not page.text:
                return None

            soup = BeautifulSoup(page.text, "html.parser")
            file_id = ""
            for inp in soup.find_all("input"):
                if inp.get("name") == "id" and inp.get("value"):
                    file_id = inp["value"].strip()
                    break

            if not file_id:
                m = re.search(r'name=["\']id["\']\s+value=["\']([^"\']+)["\']', page.text)
                if m:
                    file_id = m.group(1)

            if file_id:
                post_data = {
                    "op": "download2",
                    "id": file_id,
                    "referer": url,
                }
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": url,
                }
                # Submit download2 form to obtain 302 location or download link
                resp = await client.post(
                    "https://send.cm/",
                    data=post_data,
                    headers=headers,
                    follow_redirects=False,
                    timeout=context.timeout,
                )
                location = resp.headers.get("Location") or resp.headers.get("location")
                if location and _is_followable_http_url(location):
                    direct = location
                    hops.append(make_hop(
                        url=direct,
                        status_code=302,
                        redirect_type="sendcm_direct_redirect",
                        extra_details=f"Send.cm direct stream redirect: {file_id}",
                        hop_number=len(context.hops) + 1,
                    ))
                    return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Send.cm resolution failed: %s", exc)
        return None

    async def _resolve_skydrop(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download stream from Skydrop cloud download service."""
        try:
            parsed = urllib.parse.urlparse(url)
            base_origin = f"{parsed.scheme}://{parsed.netloc}"

            headers_base = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            if context.extra_headers:
                headers_base.update(context.extra_headers)

            # Step 1: Establish session cookies
            r1 = await client.get(url, headers=headers_base, timeout=context.timeout)
            if not r1:
                return None

            # Step 2: POST /resolve/ with XMLHttpRequest
            resolve_url = f"{base_origin}/resolve/"
            headers_xhr = dict(headers_base)
            headers_xhr.update({
                "Referer": url,
                "X-Requested-With": "XMLHttpRequest",
            })
            r2 = await client.post(resolve_url, headers=headers_xhr, timeout=context.timeout)
            payload = r2.json() if hasattr(r2, "json") else {}
            if not payload.get("success"):
                logger.debug("Skydrop /resolve/ call did not return success: %s", payload)
                return None

            ready_path = payload.get("ready_url", "/id/")
            ready_url = urllib.parse.urljoin(base_origin, ready_path)

            # Step 3: GET ready_url (/id/) to locate action form
            headers_id = dict(headers_base)
            headers_id["Referer"] = url
            r3 = await client.get(ready_url, headers=headers_id, timeout=context.timeout)
            soup = BeautifulSoup(r3.text or "", "html.parser")
            form = soup.find("form")
            action = form.get("action", "/fetch/") if form else "/fetch/"
            fetch_url = urllib.parse.urljoin(base_origin, action)

            # Step 4: POST /fetch/ to retrieve 302 location to direct storage/stream
            headers_fetch = dict(headers_base)
            headers_fetch["Referer"] = ready_url
            r4 = await client.post(fetch_url, headers=headers_fetch, follow_redirects=False, timeout=context.timeout)
            location = r4.headers.get("Location") or r4.headers.get("location")
            if location and _is_followable_http_url(location):
                direct = location
                hops.append(make_hop(
                    url=direct,
                    status_code=302,
                    redirect_type="skydrop_cloud_download",
                    extra_details="Skydrop 4-stage cloud download resolved",
                    hop_number=len(context.hops) + 1,
                ))
                return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Skydrop resolution failed: %s", exc)
        return None

    async def _resolve_racaty(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download stream from Racaty via download2 form."""
        try:
            clean_url = url.rstrip("/")
            token = clean_url.split("/")[-1]
            data = {
                "op": "download2",
                "id": token,
                "rand": "",
                "referer": "",
                "method_free": "",
                "method_premium": "",
            }
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            resp = await client.post(clean_url, headers=headers, data=data, timeout=context.timeout)
            if not resp or not resp.text:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            btn = soup.find(class_=re.compile(r"btn-dow|btn-download|dwnld"))
            if btn and btn.get("href"):
                direct = btn["href"]
                hops.append(make_hop(url=direct, status_code=200, redirect_type="racaty_direct", extra_details="Racaty direct download button extracted"))
                return direct
            unique = soup.find(id="uniqueExpirylink")
            if unique and unique.get("href"):
                direct = unique["href"]
                hops.append(make_hop(url=direct, status_code=200, redirect_type="racaty_unique_link", extra_details="Racaty expiry stream link extracted"))
                return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Racaty resolution failed: %s", exc)
        return None

    async def _resolve_solidfiles(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract downloadUrl from SolidFiles viewerOptions JSON."""
        try:
            page = await client.get(url, timeout=context.timeout)
            text = getattr(page, "text", "")
            match = re.search(r"'viewerOptions'\s*,\s*(\{[^;]+\})\s*\)\s*;", text)
            if match:
                import json
                data = json.loads(match.group(1))
                dl_url = data.get("downloadUrl")
                if dl_url and _is_followable_http_url(dl_url):
                    hops.append(make_hop(url=dl_url, status_code=200, redirect_type="solidfiles_direct", extra_details="SolidFiles direct stream extracted from viewerOptions"))
                    return dl_url
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("SolidFiles resolution failed: %s", exc)
        return None

    async def _resolve_sfile(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download link from sfile.mobi."""
        try:
            clean_url = url.rstrip("/")
            token = clean_url.split("/")[-1]
            download_page = f"https://sfile.mobi/download/{token}"
            page = await client.get(download_page, timeout=context.timeout)
            soup = BeautifulSoup(getattr(page, "text", ""), "html.parser")
            p_elem = soup.find("p")
            if p_elem and p_elem.find("a", href=True):
                dl_url = p_elem.find("a")["href"]
                if _is_followable_http_url(dl_url):
                    hops.append(make_hop(url=dl_url, status_code=200, redirect_type="sfile_direct", extra_details="SFile mobi direct download link extracted"))
                    return dl_url
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("SFile resolution failed: %s", exc)
        return None

    async def _resolve_streamsb(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract stream_data file URL from StreamSB / WatchSB mirrors."""
        try:
            import random
            clean_url = url.rstrip("/")
            if ".html" in clean_url:
                url_id = clean_url.split("/")[-1].split(".")[-2]
            else:
                url_id = clean_url.split("/")[-1]
            chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
            r1 = "".join(random.choice(chars) for _ in range(12))
            r2 = "".join(random.choice(chars) for _ in range(12))
            part_one = f"{r1}||{url_id}||{r2}||streamsb"
            hex_part = part_one.encode("utf-8").hex()
            api_endpoint = f"https://watchsb.com/sources48/{hex_part}"
            headers = {
                "watchsb": "sbstream",
                "Referer": url,
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp = await client.get(api_endpoint, headers=headers, timeout=context.timeout)
            data = resp.json() if hasattr(resp, "json") else {}
            stream_file = (data.get("stream_data") or {}).get("file")
            if stream_file and _is_followable_http_url(stream_file):
                hops.append(make_hop(url=stream_file, status_code=200, redirect_type="streamsb_direct_stream", extra_details="StreamSB / WatchSB direct video stream extracted"))
                return stream_file
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("StreamSB resolution failed: %s", exc)
        return None

    async def _resolve_fembed(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract source stream from Fembed / Fcdn JSON API."""
        try:
            clean_url = url.rstrip("/")
            token = clean_url.split("/")[-1]
            api_url = f"https://fembed-hd.com/api/source/{token}"
            resp = await client.post(api_url, timeout=context.timeout)
            data = resp.json() if hasattr(resp, "json") else {}
            items = data.get("data") or []
            if isinstance(items, list) and items:
                # Highest resolution mirror is usually last
                best = items[-1]
                dl_url = best.get("file")
                if dl_url and _is_followable_http_url(dl_url):
                    hops.append(make_hop(url=dl_url, status_code=200, redirect_type="fembed_direct_stream", extra_details=f"Fembed direct stream ({best.get('label', '')}) resolved"))
                    return dl_url
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Fembed resolution failed: %s", exc)
        return None

    async def _resolve_antfiles(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download anchor from AntFiles."""
        try:
            resp = await client.get(url, timeout=context.timeout)
            soup = BeautifulSoup(getattr(resp, "text", ""), "html.parser")
            a_elem = soup.find(class_=re.compile(r"main-btn|download"), href=True)
            if a_elem and a_elem.get("href"):
                direct = urllib.parse.urljoin(url, a_elem["href"])
                if _is_followable_http_url(direct):
                    hops.append(make_hop(url=direct, status_code=200, redirect_type="antfiles_direct", extra_details="AntFiles direct download link resolved"))
                    return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("AntFiles resolution failed: %s", exc)
        return None

    async def _resolve_mdisk(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct CDN download link from MDisk convertor API."""
        try:
            clean_url = url.rstrip("/")
            token = clean_url.split("/")[-1]
            api = f"https://diskuploader.entertainvideo.com/v1/file/cdnurl?param={token}"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            }
            resp = await client.get(api, headers=headers, timeout=context.timeout)
            data = resp.json() if hasattr(resp, "json") else {}
            dl = data.get("download")
            if dl and _is_followable_http_url(dl):
                clean_dl = dl.replace(" ", "%20")
                hops.append(make_hop(url=clean_dl, status_code=200, redirect_type="mdisk_cdn_direct", extra_details="MDisk CDN direct download stream resolved"))
                return clean_dl
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("MDisk resolution failed: %s", exc)
        return None

    async def _resolve_megaup(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
        hops: List[HopInfo],
    ) -> Optional[str]:
        """Extract direct download link from MegaUp landing page."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": url,
            }
            resp = await client.get(url, headers=headers, timeout=context.timeout)
            html = resp.text if hasattr(resp, "text") else ""
            if not html:
                return None

            # Look for direct download link patterns
            patterns = [
                r'''href=["'](https?://download\.megaup\.net/[^"']+)["']''',
                r'''["'](https?://download\.megaup\.net/\?url=[^"']+)["']''',
                r'''downloadurl\s*=\s*["'](https?://[^"']+)["']''',
                r'''window\.location\.href\s*=\s*["'](https?://download\.megaup\.net/[^"']+)["']''',
                r'''href=["'](https?://[^"']+/download/[^"']+)["']''',
            ]
            for pat in patterns:
                m = re.search(pat, html, re.IGNORECASE)
                if m:
                    direct = m.group(1).replace("&amp;", "&")
                    if _is_followable_http_url(direct):
                        hops.append(make_hop(
                            url=direct,
                            status_code=200,
                            redirect_type="megaup_direct",
                            extra_details="MegaUp direct download stream resolved",
                            hop_number=len(context.hops) + len(hops) + 1,
                        ))
                        return direct
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("MegaUp resolution failed: %s", exc)
        return None