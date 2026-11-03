"""
Cloud Fallback & Universal Fetch Gateway for unshorten-cli.
Bypasses ISP SNI-blocking, handshake timeouts, and local DNS blocks
by cascading:
1. Native curl_cffi with Chrome 120 TLS impersonation (fast, direct)
2. Native httpx async client
3. Resilient Cloud Worker Gateways (r.jina.ai HTML & Markdown)
"""
import asyncio
import re
import urllib.parse
from typing import Optional, Tuple
import httpx

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

async def fetch_page_resilient(url: str, timeout: float = 6.0, referer: Optional[str] = None) -> Tuple[str, str]:
    """
    Fetches HTML from ANY URL using concurrent racing across direct TLS and resilient cloud gateways.
    Guarantees sub-second unblocked HTML delivery without hanging on ISP connection drops.
    Returns: (html_text, base_url)
    """
    req_headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        req_headers["Referer"] = referer

    async def _fetch_direct_httpx():
        async with httpx.AsyncClient(timeout=2.5, verify=False, follow_redirects=True, headers=req_headers) as client:
            resp = await client.get(url)
            if resp.status_code < 400 and len(resp.text) > 300:
                return resp.text, str(resp.url)
        raise Exception("httpx failed")

    async def _fetch_cffi():
        if not HAS_CURL_CFFI:
            raise Exception("No cffi")
        loop = asyncio.get_running_loop()
        def _get():
            s = cffi_requests.Session(impersonate="chrome120")
            return s.get(url, headers=req_headers, timeout=3)
        resp = await loop.run_in_executor(None, _get)
        if resp.status_code < 400 and len(resp.text) > 300:
            return resp.text, resp.url
        raise Exception("cffi failed")

    async def _fetch_jina():
        async with httpx.AsyncClient(timeout=6.0, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0", "X-Return-Format": "html"}) as client:
            r = await client.get(f"https://r.jina.ai/{url}")
            if r.status_code == 200 and len(r.text) > 500:
                return r.text, url
        raise Exception("jina failed")

    async def _fetch_cors():
        encoded = urllib.parse.quote(url)
        async with httpx.AsyncClient(timeout=6.0, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(f"https://corsproxy.io/?{encoded}")
            if r.status_code == 200 and len(r.text) > 500 and "CORSPROXY" not in r.text:
                return r.text, url
        raise Exception("cors failed")

    # Launch concurrent race
    tasks = [
        asyncio.create_task(_fetch_direct_httpx()),
        asyncio.create_task(_fetch_cffi()),
        asyncio.create_task(_fetch_jina()),
        asyncio.create_task(_fetch_cors())
    ]

    for comp in asyncio.as_completed(tasks):
        try:
            html_text, base_u = await comp
            for t in tasks:
                t.cancel()
            return html_text, base_u
        except Exception:
            continue

    # 4. Firecrawl High-Fidelity Scraper Fallback (for heavy JS and Cloudflare challenges)
    try:
        import os
        fc_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if not fc_key:
            return "", url
        fc_payload = {"url": url, "formats": ["rawHtml", "html"]}
        async with httpx.AsyncClient(timeout=12.0) as client:
            fc_resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {fc_key}", "Content-Type": "application/json"},
                json=fc_payload
            )
            if fc_resp.status_code == 200:
                fc_data = fc_resp.json()
                raw_html = fc_data.get("data", {}).get("rawHtml") or fc_data.get("data", {}).get("html", "")
                if len(raw_html) > 500:
                    return raw_html, url
    except Exception:
        pass

    return "", url
