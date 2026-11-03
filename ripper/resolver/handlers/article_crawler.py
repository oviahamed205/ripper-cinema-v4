"""
Intermediate Server Page & Article Crawler for Ripper Resolver.
Resolves multi-button landing pages, movie articles, and server mirrors
all the way down to direct playable streams.
"""
from __future__ import annotations

import asyncio
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpx
from bs4 import BeautifulSoup

from ..core import (
    _clean_extracted_url,
    _is_followable_http_url,
    coerce_timeout,
    default_headers,
    extract_filename_from_url_or_headers,
    extract_url_from_query_params,
    host_of,
    is_ad_trap,
    is_direct_file_url,
    is_direct_storage_url,
    is_hidden_element,
    pick_fastest_live_mirror,
    request_capped_with_client,
    validate_presigned_url,
    DOWNLOAD_EXTENSIONS,
)
from .hubcloud import HubCloudHandler
from .kmhd import resolve_kmhd_page
from .magiclinks import resolve_magiclinks_page
from .nexdrive import resolve_nexdrive_page
from .vcloud import resolve_vcloud_page
from ...index_crawler import is_directory_index, parse_directory_index
from ...models import ServerMirror


SERVER_BTN_CLASSES = {
    "server-btn", "btn-cloud", "download-now", "btn-download",
    "dlink", "download_link", "btn-server",
}
SERVER_BTN_KEYWORDS = [
    "cloud", "resumable", "download", "server", "fast", "mirror",
    "1080p", "720p", "480p", "stream", "drive", "direct",
]

_CLOUD_URL_REGEXES = (
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.r2\.cloudflarestorage\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.r2\.dev/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.s3[a-zA-Z0-9.\-]*\.amazonaws\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://storage\.googleapis\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.backblazeb2\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.wasabisys\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.digitaloceanspaces\.com/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]+\.b-cdn\.net/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://pixeldrain\.(?:com|dev)/(?:api/file/|u/|l/)[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://(?:www\.)?gofile\.io/d/[a-zA-Z0-9_-]+', re.I),
    re.compile(r'https?://(?:www\.)?megaup\.net/[a-zA-Z0-9_-]+', re.I),
    re.compile(r'https?://(?:www\.)?mediafire\.com/file/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://(?:www\.)?krakenfiles\.com/view/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*hubcloud\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*vcloud\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*fast-?dl\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*filepress\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*katdrive\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[a-zA-Z0-9.\-]*gdtot\.[a-zA-Z0-9.\-]+/[^\s"\'<>\\]+', re.I),
    re.compile(r'https?://[^\s"\'<>\\]+/cdn-cgi/content/[^\s"\'<>\\]+', re.I),
)

_DIRECT_FILE_IN_HTML_RE = re.compile(
    r'https?://[^\s"\'<>\\]+?\.(?:mkv|mp4|webm|avi|mov|ts|m4v|zip|rar|7z)(?:\?[^\s"\'<>\\]*)?',
    re.I,
)


def extract_cloud_urls_from_html(html_content: str) -> List[str]:
    """Return unique presigned / direct storage URLs found in HTML or scripts."""
    if not html_content:
        return []
    found: List[str] = []
    seen: Set[str] = set()
    for pattern in _CLOUD_URL_REGEXES:
        for match in pattern.findall(html_content):
            cleaned = _clean_extracted_url(match)
            if cleaned and cleaned not in seen and _is_followable_http_url(cleaned):
                seen.add(cleaned)
                found.append(cleaned)
    for match in _DIRECT_FILE_IN_HTML_RE.findall(html_content):
        cleaned = _clean_extracted_url(match)
        if cleaned and cleaned not in seen and _is_followable_http_url(cleaned) and not is_ad_trap(cleaned):
            seen.add(cleaned)
            found.append(cleaned)
    return found


def extract_server_options_from_html(html_content: str, base_url: str) -> List[Tuple[str, str]]:
    """
    Detects download server buttons, cloud mirrors, and direct links from landing pages.
    Filters out honeypots and hidden CSS elements.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    candidates: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    for element in soup.find_all(["a", "button"]):
        if is_hidden_element(element):
            continue

        href = element.get("href") or element.get("data-url") or element.get("data-href") or element.get("data-link") or ""
        classes = " ".join(element.get("class", [])).lower()
        onclick = element.get("onclick", "") or ""
        text = element.get_text(separator=" ").strip()
        text_lower = text.lower()

        if onclick and not href:
            match = re.search(r'["\x27](https?://[^\s"\x27]+|/[^\s"\x27]+)["\x27]', onclick)
            if match:
                href = match.group(1)

        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        full_url = _clean_extracted_url(urllib.parse.urljoin(base_url, href))
        if not _is_followable_http_url(full_url) or full_url in seen or is_ad_trap(full_url):
            continue

        has_server_class = any(item in classes for item in SERVER_BTN_CLASSES)
        has_server_keyword = any(keyword in text_lower for keyword in SERVER_BTN_KEYWORDS)
        is_direct_storage = is_direct_storage_url(full_url) or is_direct_file_url(full_url)
        is_cdn_cgi = "cdn-cgi/content" in full_url

        if has_server_class or has_server_keyword or is_direct_storage or is_cdn_cgi:
            if text and len(text) < 40:
                label = text
            elif is_cdn_cgi:
                label = "OMDrive Direct Link"
            else:
                label = "Direct Download Server"
            candidates.append((label, full_url))
            seen.add(full_url)

    return candidates


async def _crawl_media_article(
    client: httpx.AsyncClient,
    html_body: str,
    page_url: str,
    headers: Dict[str, str],
    timeout: float,
    depth: int,
    max_depth: int,
) -> Optional[str]:
    """Resolve a movie-article page through the optional ripper.media helper."""
    try:
        from ...media import extract_media_items_from_html, resolve_single_media_item_fast
    except Exception:
        return None
    try:
        items = extract_media_items_from_html(html_body, page_url)
        if not items:
            return None
        best_index = 0
        for index, item in enumerate(items):
            quality = getattr(item, "quality", "") or ""
            codec = getattr(item, "codec", "") or ""
            if "1080" in str(quality) and "HQ-LOW" not in str(codec):
                best_index = index
                break
        chosen = items[best_index]
        resolved = await resolve_single_media_item_fast(chosen, client, timeout=timeout, headers=headers)
        servers = getattr(resolved, "servers", None) or []
        for server in servers:
            direct = getattr(server, "direct_download_url", None)
            if direct:
                return direct
        landing = getattr(resolved, "unshortened_landing_url", None)
        if landing:
            crawled = await crawl_intermediate_server_page(
                client, landing, headers, timeout=timeout, _depth=depth + 1, _max_depth=max_depth
            )
            if crawled:
                return crawled
        if servers:
            first_intermediate = getattr(servers[0], "intermediate_url", None)
            if first_intermediate:
                return await crawl_intermediate_server_page(
                    client,
                    first_intermediate,
                    headers,
                    timeout=timeout,
                    _depth=depth + 1,
                    _max_depth=max_depth,
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    return None


async def crawl_intermediate_server_page(
    client: httpx.AsyncClient,
    intermediate_url: str,
    headers: Dict[str, str],
    timeout: float = 6.0,
    _depth: int = 0,
    _max_depth: int = 3,
) -> Optional[str]:
    """Fetch an intermediate download page and extract a direct storage stream."""
    if not intermediate_url or _depth >= _max_depth:
        return None
    if is_ad_trap(intermediate_url):
        return None
    if is_direct_storage_url(intermediate_url) or is_direct_file_url(intermediate_url):
        return intermediate_url

    try:
        lowered = intermediate_url.lower()

        # Check Pixeldrain
        if "pixeldrain.com/u/" in lowered or "pixeldrain.dev/u/" in lowered:
            m_px = re.search(r"pixeldrain\.(?:com|dev)/u/([a-zA-Z0-9_-]+)", intermediate_url)
            if m_px:
                return f"https://pixeldrain.com/api/file/{m_px.group(1)}?download"

        # Check Streamtape
        if "streamtape.com" in lowered:
            st_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if st_page.text:
                m_st = re.search(r"document\.getElementById\(['\"]robotlink['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]\s*\+\s*\(['\"]([^'\"]+)['\"]\)\.substring\(2\)\.substring\(1\)", st_page.text)
                if m_st:
                    return "https:" + m_st.group(1) + m_st.group(2)[3:]
                m_st_simple = re.search(r"getElementById\(['\"]robotlink['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]", st_page.text)
                if m_st_simple:
                    st_val = m_st_simple.group(1)
                    return "https:" + st_val if st_val.startswith("//") else st_val

        # Check Streamwish
        if any(w in lowered for w in ["streamwish", "hglink.to", "swish"]):
            sw_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if sw_page.text:
                m_m3u8 = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', sw_page.text)
                if m_m3u8:
                    return m_m3u8.group(1)

        # Check 1fichier (Direct download form or inline bypass)
        if "1fichier.com" in lowered:
            fic_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if fic_page.text:
                m_fic = re.search(r'href=["\x27](https?://[a-zA-Z0-9.\-]+\.1fichier\.com/[a-zA-Z0-9_-]+)["\x27][^>]*class=["\x27][^"\x27]*ok', fic_page.text)
                if m_fic:
                    return m_fic.group(1)

        # Check GoFile
        if "gofile.io/d/" in lowered:
            m_gf = re.search(r"gofile\.io/d/([a-zA-Z0-9_-]+)", intermediate_url)
            if m_gf:
                content_id = m_gf.group(1)
                try:
                    tok_resp = await client.post("https://api.gofile.io/accounts", headers=headers, timeout=timeout)
                    if tok_resp.status_code == 200 and tok_resp.json().get("status") == "ok":
                        wt_token = tok_resp.json().get("data", {}).get("token")
                        if wt_token:
                            c_resp = await client.get(
                                f"https://api.gofile.io/contents/{content_id}?wt={wt_token}",
                                headers=headers,
                                timeout=timeout,
                            )
                            if c_resp.status_code == 200 and c_resp.json().get("status") == "ok":
                                children = c_resp.json().get("data", {}).get("children", {})
                                for child_id, child_info in children.items():
                                    direct_dl = child_info.get("link")
                                    if direct_dl:
                                        return direct_dl
                except Exception:
                    pass

        # Check Doodstream
        if any(d in lowered for d in ["doodstream.com", "dood.to", "dood.so", "dood.la", "dood.ws", "dood.wf"]):
            dood_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if dood_page.text:
                m_pass = re.search(r"/pass_md5/([^'\"]+)", dood_page.text)
                if m_pass:
                    pass_url = f"https://dood.to/pass_md5/{m_pass.group(1)}"
                    pass_resp = await client.get(pass_url, headers={**headers, "Referer": intermediate_url}, timeout=timeout)
                    if pass_resp.status_code == 200 and pass_resp.text:
                        import time
                        token = m_pass.group(1).split("/")[-1]
                        return f"{pass_resp.text.strip()}?token={token}&expiry={int(time.time()*1000)}"

        # Check Bunkr
        if any(b in lowered for b in ["bunkr.is", "bunkr.black", "bunkr.cr", "bunkr.ru", "bunkr.site"]):
            bunkr_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if bunkr_page.text:
                m_bunk = re.search(r'href=["\x27](https?://media-files[a-zA-Z0-9.\-]+\.bunkr\.[a-z]+/[^"\x27]+)["\x27]', bunkr_page.text)
                if not m_bunk:
                    m_bunk = re.search(r'src=["\x27](https?://media-files[a-zA-Z0-9.\-]+\.bunkr\.[a-z]+/[^"\x27]+)["\x27]', bunkr_page.text)
                if m_bunk:
                    return m_bunk.group(1)

        # Check Mega.nz
        if "mega.nz/file/" in lowered:
            m_mega = re.search(r"mega\.nz/file/([a-zA-Z0-9_-]+)#([a-zA-Z0-9_-]+)", intermediate_url)
            if m_mega:
                file_id, file_key = m_mega.group(1), m_mega.group(2)
                try:
                    payload = [{"a": "g", "g": 1, "p": file_id}]
                    api_resp = await client.post(
                        "https://g.api.mega.co.nz/cs",
                        json=payload,
                        headers=headers,
                        timeout=timeout,
                    )
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        if isinstance(data, list) and data and "g" in data[0]:
                            return data[0]["g"]
                except Exception:
                    pass

        # Check SendCM
        if "send.cm" in lowered:
            send_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if send_page.text:
                m_send = re.search(r'href=["\x27](https?://[a-zA-Z0-9.\-]+\.send\.cm/d/[a-zA-Z0-9_-]+/[^"\x27]+)["\x27]', send_page.text)
                if m_send:
                    return m_send.group(1)

        # Check KMHD
        if "kmhd" in lowered or "katdrive" in lowered:
            kmhd_mirrors = await resolve_kmhd_page(client, intermediate_url, headers, timeout=timeout)
            for m in kmhd_mirrors:
                if m.direct_download_url:
                    return m.direct_download_url
            if kmhd_mirrors:
                return kmhd_mirrors[0].intermediate_url

        # Check MagicLinks
        if "magiclinks" in lowered:
            magic_mirrors = await resolve_magiclinks_page(client, intermediate_url, headers, timeout=timeout)
            for m in magic_mirrors:
                if m.direct_download_url:
                    return m.direct_download_url
            if magic_mirrors:
                return magic_mirrors[0].intermediate_url

        # Check V-Cloud
        if "vcloud" in lowered:
            vcloud_mirrors = await resolve_vcloud_page(client, intermediate_url, headers, timeout=timeout)
            for m in vcloud_mirrors:
                if m.direct_download_url:
                    return m.direct_download_url
            if vcloud_mirrors:
                return vcloud_mirrors[0].intermediate_url

        # Check NexDrive
        if "nexdrive" in lowered:
            nex_mirrors = await resolve_nexdrive_page(client, intermediate_url, headers, timeout=timeout)
            for m in nex_mirrors:
                if m.direct_download_url:
                    return m.direct_download_url
            if nex_mirrors:
                return nex_mirrors[0].intermediate_url

        # Check MobileJSR (7StarHD shortener / gateway)
        if "mobilejsr.com" in lowered:
            mjsr_page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
            if mjsr_page.text:
                m_cgi = re.search(r'href=["\x27](https?://mobilejsr\.com/cdn-cgi/content\?[^"\x27]+)["\x27]', mjsr_page.text)
                if m_cgi:
                    return m_cgi.group(1)
                m_rel = re.search(r'href=["\x27](/cdn-cgi/content\?[^"\x27]+)["\x27]', mjsr_page.text)
                if m_rel:
                    return urllib.parse.urljoin(intermediate_url, m_rel.group(1))

        # Check HubCloud / CineCloud
        if any(marker in lowered for marker in ["hubcloud", "hubdrive", "gamerxyt", "cinecloud", "neodrive"]):
            hub_handler = HubCloudHandler()
            from ..base import ResolutionContext
            ctx = ResolutionContext(timeout=timeout, extra_headers=headers)
            step_result = await hub_handler.resolve(intermediate_url, client, ctx)
            if step_result and step_result[0]:
                return step_result[0]

        # Fetch page with size-capped reader
        page = await request_capped_with_client(client, intermediate_url, headers, timeout, follow_redirects=True)
        final_url = page.url or intermediate_url
        if page.is_binary or is_direct_storage_url(final_url) or is_direct_file_url(final_url):
            return final_url

        # Scan for direct cloud storage links in body
        for cloud_url in extract_cloud_urls_from_html(page.text or ""):
            return cloud_url

        # Check directory indexes
        if is_directory_index(page.text or ""):
            dir_entries = parse_directory_index(page.text or "", final_url)
            if dir_entries:
                return dir_entries[0][1]

        # Scan server options
        options = extract_server_options_from_html(page.text or "", final_url)
        for label, opt_url in options:
            if is_direct_storage_url(opt_url) or is_direct_file_url(opt_url):
                return opt_url

        # Check movie article
        media_direct = await _crawl_media_article(
            client, page.text or "", final_url, headers, timeout, _depth, _max_depth
        )
        if media_direct:
            return media_direct

    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    return None


async def resolve_to_direct_stream_url(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 6.0,
) -> str:
    """
    Universal Direct Video Stream Resolver:
    Takes ANY intermediate download page URL, shortener, or generator link and
    resolves it all the way down to a playable direct stream (Cloudflare R2,
    AWS S3, PixelDrain direct API, GoFile CDN, direct .mkv/.mp4 link).
    """
    if not url:
        return ""
    clean_url = url.strip()

    # Dynamic Domain Remapping via Auto-Hoster Watchdog
    try:
        from ...hoster_watchdog import remap_hoster_url
        clean_url = remap_hoster_url(clean_url)
    except Exception:
        pass

    if is_direct_file_url(clean_url) or is_direct_storage_url(clean_url):
        return clean_url

    request_headers = headers or default_headers()
    if client:
        direct = await crawl_intermediate_server_page(client, clean_url, request_headers, timeout=timeout)
        return direct or clean_url

    timeout_obj = coerce_timeout(timeout)
    async with httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True) as fresh_client:
        direct = await crawl_intermediate_server_page(fresh_client, clean_url, request_headers, timeout=timeout)
        return direct or clean_url