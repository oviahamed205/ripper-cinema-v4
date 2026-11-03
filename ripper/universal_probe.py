"""
Universal Fallback Media Extractor for unshorten-cli.
Heuristically inspects any unknown webpage for HTML5 video elements,
embedded iframes, JWPlayer/VideoJS setup blocks, and packed JavaScript.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import List, Dict, Optional, Any
import httpx
from bs4 import BeautifulSoup


def unpack_dean_edwards_js(p: str, a: int, c: int, k: list, e=None, d=None) -> str:
    """Standard unpacker for Dean Edwards p.a.c.k.e.r."""
    def e_fn(c):
        return ('' if c < a else e_fn(c // a)) + (chr(c % a + 29) if c % a > 35 else '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'[c % a])
    d = {}
    while c > 0:
        c -= 1
        d[e_fn(c)] = k[c] if k[c] else e_fn(c)
    return re.sub(r'\b(\w+)\b', lambda m: d.get(m.group(0), m.group(0)), p)


async def probe_page_for_media(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 8.0,
) -> List[Dict[str, Any]]:
    """
    Universally probe a webpage and return a list of extracted playable streams.
    """
    results: List[Dict[str, Any]] = []
    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True)
        close_client = True

    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": url})
        html = resp.text
        base_url = str(resp.url)

        # 1. HTML5 <video> and <source> tags
        soup = BeautifulSoup(html, "html.parser")
        for v in soup.find_all(["video", "source"]):
            src = v.get("src") or v.get("data-src")
            if src:
                full_src = urllib.parse.urljoin(base_url, src)
                if any(ext in full_src.lower() for ext in (".mp4", ".m3u8", ".mkv", ".webm")):
                    results.append({
                        "title": "HTML5 Video Source",
                        "url": full_src,
                        "type": "Direct Media Stream",
                        "confidence": 95,
                    })

        # 2. JavaScript JWPlayer / VideoJS / HLS configurations
        m_sources = re.findall(r'["\']?(?:file|src|source)["\']?\s*:\s*["\'](https?://[^"\'\s<>]+?\.(?:m3u8|mp4|mkv)[^"\'\s<>]*)["\']', html)
        for s in m_sources:
            results.append({
                "title": "JWPlayer / HLS Stream",
                "url": s,
                "type": "HLS / Direct Stream",
                "confidence": 90,
            })

        # 3. Dean Edwards Packer scan
        m_pack = re.search(r'eval\(function\(p,a,c,k,e,d\).*?\}\((.*?)\)\)', html, re.DOTALL)
        if m_pack:
            try:
                # Look for stream patterns inside packed JS
                raw_args = m_pack.group(1)
                packed_streams = re.findall(r'["\'](https?://[^"\'\s<>]+?\.(?:m3u8|mp4)[^"\'\s<>]*)["\']', raw_args)
                for ps in packed_streams:
                    results.append({
                        "title": "Unpacked Media Stream",
                        "url": ps,
                        "type": "Direct Master Stream",
                        "confidence": 92,
                    })
            except Exception:
                pass

        # 4. Embedded Video Iframes
        for ifr in soup.find_all("iframe"):
            src = ifr.get("src")
            if src and any(h in src.lower() for h in ("embed", "player", "stream", "video", "play")):
                full_ifr = urllib.parse.urljoin(base_url, src)
                results.append({
                    "title": "Embedded Video Player",
                    "url": full_ifr,
                    "type": "Embed Player Frame",
                    "confidence": 80,
                })

    except Exception:
        pass
    finally:
        if close_client:
            await client.aclose()

    # Deduplicate by URL
    seen = set()
    deduped = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)
    return deduped
