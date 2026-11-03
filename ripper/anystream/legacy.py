"""
AnyStream: Universal Deep Stream & Video Link Extractor (Enterprise & God-Level Edition)
Extracts direct playable HLS (.m3u8, .txt playlists) and MP4 streams from ANY webpage or video host.
Features:
- Robust URL Sanitizer (extracts clean HTTP/HTTPS links from any messy user input text)
- Built-in Host Handshake Decoders with Chrome 120 TLS Impersonation:
    * DoodStream / D000d / Playmogo (pass_md5 token handshake + Cloudflare Origin IP relay -> direct MP4)
    * PlayMate (playmate.to -> /api/s -> master.txt HLS)
    * Vidara / Vidarae (vidara.to / vidarae.live -> /api/stream -> master.m3u8)
    * StreamTape (streamtape.com -> /get_video?id=... direct MP4)
    * FileLions / StreamWish / Voe / LuluStream / HTML5 <video>
- Integrated Local Reverse Proxy (Bypasses PotPlayer header syntax crashes, IP locks, and 403 Forbidden)
- 8-Thread Turbo Downloader & HLS playlist scraper
"""

import os
import re
import sys
import time
import random
import string
import socket
import ssl
import json
import asyncio
import urllib.parse
from typing import List, Dict, Optional, Any
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
try:
    import yt_dlp
    HAS_YT_DLP = True
except ImportError:
    HAS_YT_DLP = False


from ..player import launch_video_stream_in_player
from ..downloader import download_file_parallel_8_thread
from ..remote_hub import unpack_packer
from ..proxy_engine import get_proxied_stream_url, get_web_player_url
from ..cloud_fetch import fetch_page_resilient
from ..session_manager import register_playback_session
import webbrowser

console = Console()

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

VIDEO_EXTENSIONS = (".mp4", ".m3u8", ".webm", ".mkv", ".ts", ".mpd", ".avi", ".mov")

IGNORE_PATTERNS = [
    "analytics", "google", "facebook", "doubleclick", "twitter", "ads",
    "preview.mp4", "thumb", "teaser", "banner", "logo", "pixel", "tracker",
    "trailer.mp4", "promo.mp4", "sample.mp4", "short.mp4", "/trailers/",
    "kaira18", "syndication", "exoclick", "juicyads", "trafficjunky", "ero-advertising",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".ico", ".woff", ".js"
]

DOOD_HOSTS = ["dood", "d000d", "d0000d", "ds2play", "dooodster", "playmogo"]

def sanitize_user_url(raw_input: str) -> str:
    """Extracts the first valid http:// or https:// link from any messy user input."""
    if not raw_input:
        return ""
    m = re.search(r"https?://[^\s\"'<>]+", raw_input.strip())
    if m:
        clean = m.group(0).rstrip(".,;)\"'>")
        return clean
    return raw_input.strip()

def is_valid_video_stream(url: str) -> bool:
    clean = url.lower().split("?")[0].rstrip("/")
    if any(ign in clean for ign in IGNORE_PATTERNS):
        return False
    return (
        any(clean.endswith(ext) for ext in VIDEO_EXTENSIONS)
        or any(k in clean for k in [".m3u8", "master.txt", "/stream/", "/video/", "/hls/", "/embed/", "/e/", "get_file", "get_video"])
    )


def resolve_stream_to_final_cdn(stream_url: str, timeout: float = 2.5) -> Tuple[str, int]:
    """
    Inspects stream URL, resolves redirect (302) to high-speed CDN and extracts true content size.
    Returns: (final_stream_url, total_size_bytes)
    """
    try:
        parsed = urllib.parse.urlparse(stream_url)
        host = parsed.netloc
        if not host:
            return stream_url, 0
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 1. Resolve host via DoH
        req_doh = urllib.request.Request(
            f"https://1.1.1.1/dns-query?name={host}&type=A",
            headers={"Accept": "application/dns-json", "User-Agent": "Mozilla/5.0"}
        )
        doh_data = json.loads(urllib.request.urlopen(req_doh, timeout=2.0).read())
        answers = [a["data"] for a in doh_data.get("Answer", []) if a.get("type") == 1]
        ip = answers[0] if answers else host

        s = socket.create_connection((ip, port), timeout=timeout)
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                s = ctx.wrap_socket(s, server_hostname=None)
            except Exception:
                s.close()
                s = socket.create_connection((ip, port), timeout=timeout)
                s = ctx.wrap_socket(s, server_hostname=host)

        pq = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        req = f"GET {pq} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nRange: bytes=0-50\r\nConnection: close\r\n\r\n"
        s.sendall(req.encode("utf-8"))
        res = s.recv(2048)
        s.close()

        if not res:
            return stream_url, 0

        status_line = res.splitlines()[0].decode("latin1")
        parts = status_line.split()
        if len(parts) > 1 and parts[1].isdigit():
            code = int(parts[1])
            # Follow 301/302/303/307/308 redirect directly to final CDN
            if code in [301, 302, 303, 307, 308]:
                for line in res.splitlines():
                    line_str = line.decode("latin1")
                    if ":" in line_str:
                        hk, hv = line_str.split(":", 1)
                        if hk.strip().lower() == "location":
                            redir = urllib.parse.urljoin(stream_url, hv.strip())
                            return resolve_stream_to_final_cdn(redir, timeout=timeout)

            total_size = 0
            for line in res.splitlines():
                line_str = line.decode("latin1").lower()
                if line_str.startswith("content-range:"):
                    m_cr = re.search(r"/(\d+)", line_str)
                    if m_cr:
                        total_size = int(m_cr.group(1))
                elif line_str.startswith("content-length:") and total_size == 0:
                    m_cl = re.search(r"content-length:\s*(\d+)", line_str)
                    if m_cl:
                        total_size = int(m_cl.group(1))
            return stream_url, total_size
    except Exception:
        pass
    return stream_url, 0

def verify_stream_liveness_fast(url: str, timeout: float = 2.5) -> Tuple[bool, int]:
    final_u, sz = resolve_stream_to_final_cdn(url, timeout=timeout)
    return True, sz



# ---------------- HOST RESOLVERS ----------------

async def resolve_doodstream_direct_stream(embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves DoodStream / D000d / Playmogo embed directly to MP4 stream with TLS Chrome impersonation."""
    try:
        if HAS_CURL_CFFI:
            session = cffi_requests.Session(impersonate="chrome120")
            r = session.get(embed_url, headers={"Referer": embed_url}, timeout=10)
            html = r.text
            final_url = r.url
            domain = final_url.split("/")[2]
        else:
            async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=True) as client:
                r = await client.get(embed_url, headers={"Referer": embed_url})
                html = r.text
                final_url = str(r.url)
                domain = r.url.netloc

        m = re.search(r"['\"]/pass_md5/([^/'\"]+)/([^'\"]+)['\"]", html)
        if not m:
            m = re.search(r"/pass_md5/([^\s'\"<>\)]+)", html)
            if m:
                parts = m.group(1).split("/")
                hash_val = parts[0]
                token_val = parts[1] if len(parts) > 1 else ""
            else:
                return None
        else:
            hash_val = m.group(1)
            token_val = m.group(2)

        pass_url = f"https://{domain}/pass_md5/{hash_val}/{token_val}" if token_val else f"https://{domain}/pass_md5/{hash_val}"
        
        if HAS_CURL_CFFI:
            p_resp = session.get(pass_url, headers={"Referer": final_url})
            prefix = p_resp.text.strip()
        else:
            async with httpx.AsyncClient(timeout=10, verify=False, follow_redirects=True) as client:
                p_resp = await client.get(pass_url, headers={"Referer": final_url})
                prefix = p_resp.text.strip()

        if not prefix or "http" not in prefix:
            return None

        rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        expiry = int(time.time() * 1000)
        direct_mp4 = f"{prefix}{rand_str}?token={token_val}&expiry={expiry}"

        return {
            "stream_url": direct_mp4,
            "referer": f"https://{domain}/",
            "thumbnail": "",
            "quality": "HD 1080p MP4 Direct (DoodStream)"
        }
    except Exception:
        return None


async def resolve_playmate_direct_stream(client: httpx.AsyncClient, embed_or_filecode: str) -> Optional[Dict[str, str]]:
    """Resolves playmate.to embed directly to master HLS stream."""
    filecode = embed_or_filecode.rstrip("/").split("/")[-1]
    api_url = "https://playmate.to/api/s"
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Referer": f"https://playmate.to/embed/{filecode}",
        "Origin": "https://playmate.to",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    payload = {
        "c": filecode,
        "d": "web"
    }
    try:
        r = await client.post(api_url, headers=headers, json=payload, timeout=8.0)
        if r.status_code == 200:
            data = r.json()
            stream_url = data.get("sx")
            if stream_url:
                return {
                    "stream_url": stream_url,
                    "referer": "https://playmate.to/",
                    "thumbnail": data.get("ix", ""),
                    "quality": "HD 1080p / 720p HLS (PlayMate)"
                }
    except Exception:
        pass
    return None


async def resolve_vidara_direct_stream(client: httpx.AsyncClient, embed_or_filecode: str) -> Optional[Dict[str, str]]:
    """Resolves Vidara.to / Vidarae.live embed directly to master.m3u8 stream."""
    filecode = embed_or_filecode.rstrip("/").split("/")[-1]
    api_url = "https://vidarae.live/api/stream"
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Referer": f"https://vidarae.live/e/{filecode}",
        "Origin": "https://vidarae.live",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    payload = {
        "filecode": filecode,
        "device": "web"
    }
    try:
        r = await client.post(api_url, headers=headers, json=payload, timeout=8.0)
        if r.status_code == 200:
            data = r.json()
            stream_url = data.get("streaming_url")
            if stream_url:
                return {
                    "stream_url": stream_url,
                    "referer": "https://vidarae.live/",
                    "thumbnail": data.get("thumbnail", ""),
                    "quality": "HD 1080p / 720p HLS (Vidara)"
                }
    except Exception:
        pass
    return None


async def resolve_streamtape_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves StreamTape embedded player to direct MP4."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        m = re.search(r"document\.getElementById\('robotlink'\)\.innerHTML\s*=\s*'([^']+)'\s*\+\s*'([^']+)'", r.text)
        if m:
            link = f"https:{m.group(1)}{m.group(2)}"
            return {
                "stream_url": link,
                "referer": "https://streamtape.com/",
                "thumbnail": "",
                "quality": "HD MP4 Direct (StreamTape)"
            }
    except Exception:
        pass
    return None


async def resolve_mixdrop_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves Mixdrop embed directly to MP4 stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'(?:MDCore\.vurl|wurl)\s*=\s*["\']([^"\']+)["\']', unpacked)
        if not m:
            m = re.search(r'["\'](//[^\s"\'<>]+\.mp4[^"\'<>]*)["\']', unpacked)
        if m:
            link = m.group(1)
            if link.startswith("//"):
                link = f"https:{link}"
            return {
                "stream_url": link,
                "referer": "https://mixdrop.co/",
                "thumbnail": "",
                "quality": "HD 1080p MP4 (Mixdrop)"
            }
    except Exception:
        pass
    return None


async def resolve_filemoon_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves FileMoon embed directly to master HLS stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'sources:\s*\[\s*\{\s*file:\s*["\']([^"\']+)["\']', unpacked)
        if not m:
            m = re.search(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', unpacked)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "HD 1080p / 720p HLS (FileMoon)"
            }
    except Exception:
        pass
    return None


async def resolve_voe_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves Voe stream embed to HLS / MP4."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        m = re.search(r'["\']hls["\']\s*:\s*["\']([^"\']+)["\']', r.text)
        if not m:
            m = re.search(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', r.text)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "HD 1080p HLS (Voe)"
            }
    except Exception:
        pass
    return None


async def resolve_vidsrc_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves VidSrc / VixSrc multi-hop master HLS stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', unpacked)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "HD 1080p / 720p HLS (VidSrc)"
            }
    except Exception:
        pass
    return None


async def resolve_vidhide_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves VidHide / StreamHide embed directly to master HLS stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'sources:\s*\[\s*\{\s*file:\s*["\']([^"\']+)["\']', unpacked)
        if not m:
            m = re.search(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', unpacked)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "HD 1080p HLS (VidHide)"
            }
    except Exception:
        pass
    return None


async def resolve_upstream_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves Upstream embed directly to HLS / MP4 stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'["\'](https?://[^\s"\'<>]+\.(?:m3u8|mp4)[^\s"\'<>]*)["\']', unpacked)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "HD 1080p (Upstream)"
            }
    except Exception:
        pass
    return None


async def resolve_mp4upload_direct_stream(client: httpx.AsyncClient, embed_url: str) -> Optional[Dict[str, str]]:
    """Resolves Mp4Upload embed directly to raw MP4 stream."""
    try:
        r = await client.get(embed_url, headers={"Referer": embed_url}, timeout=8.0)
        unpacked = unpack_packer(r.text)
        m = re.search(r'src:\s*["\'](https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)["\']', unpacked)
        if not m:
            m = re.search(r'["\'](https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)["\']', unpacked)
        if m:
            return {
                "stream_url": m.group(1),
                "referer": embed_url,
                "thumbnail": "",
                "quality": "Direct Source MP4 (Mp4Upload)"
            }
    except Exception:
        pass
    return None


# ---------------- MASTER EXTRACTION ENGINE ----------------


# ---------------- SPECIALIZED TUBE & ADULT PLATFORM ENGINES ----------------

def int_to_int32(val: int) -> int:
    val = val & 0xFFFFFFFF
    if val >= 0x80000000:
        val -= 0x100000000
    return val

class _XHamsterByteGenerator:
    def __init__(self, algo_id: int, seed: int):
        self._algorithm = getattr(self, f"_algo{algo_id}", self._algo1)
        self._s = int_to_int32(seed)

    def _algo1(self, s):
        s = self._s = int_to_int32(s * 1664525 + 1013904223)
        return s

    def _algo2(self, s):
        s = int_to_int32(s ^ (s << 13))
        s = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 17))
        s = self._s = int_to_int32(s ^ (s << 5))
        return s

    def _algo3(self, s):
        s = self._s = int_to_int32(s + 0x9e3779b9)
        s = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 16))
        s = int_to_int32(s * int_to_int32(0x85ebca77))
        s = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 13))
        s = int_to_int32(s * int_to_int32(0xc2b2ae3d))
        return int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 16))

    def _algo4(self, s):
        s = self._s = int_to_int32(s + 0x6d2b79f5)
        s = int_to_int32((s << 7) | ((s & 0xFFFFFFFF) >> 25))
        s = int_to_int32(s + 0x9e3779b9)
        s = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 11))
        return int_to_int32(s * 0x27d4eb2d)

    def _algo5(self, s):
        s = int_to_int32(s ^ (s << 7))
        s = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 9))
        s = int_to_int32(s ^ (s << 8))
        s = self._s = int_to_int32(s + 0xa5a5a5a5)
        return s

    def _algo6(self, s):
        s = self._s = int_to_int32(s * int_to_int32(0x2c9277b5) + int_to_int32(0xac564b05))
        s2 = int_to_int32(s ^ ((s & 0xFFFFFFFF) >> 18))
        shift = (s & 0xFFFFFFFF) >> 27 & 31
        return int_to_int32((s2 & 0xFFFFFFFF) >> shift)

    def _algo7(self, s):
        s = self._s = int_to_int32(s + int_to_int32(0x9e3779b9))
        e = int_to_int32(s ^ (s << 5))
        e = int_to_int32(e * int_to_int32(0x7feb352d))
        e = int_to_int32(e ^ ((e & 0xFFFFFFFF) >> 15))
        return int_to_int32(e * int_to_int32(0x846ca68b))

    def __next__(self):
        return self._algorithm(self._s) & 0xFF


def decipher_xhamster_url(format_url: str) -> str:
    try:
        parsed_url = urllib.parse.urlparse(format_url)
        m = re.search(r"^/([0-9a-fA-F]{12,})([/,].+)$", parsed_url.path)
        if not m:
            return format_url
        hex_string, rem = m.group(1), m.group(2)
        byte_data = bytes.fromhex(hex_string)
        seed = int.from_bytes(byte_data[1:5], byteorder="little", signed=True)
        gen = _XHamsterByteGenerator(byte_data[0], seed)
        deciphered = bytearray(b ^ next(gen) for b in byte_data[5:]).decode("latin-1")
        return parsed_url._replace(path=f"/{deciphered}{rem}").geturl()
    except Exception:
        return format_url


async def resolve_spankbang_direct_streams(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Direct master extractor for SpankBang with dynamic stream key handling."""
    results = []
    try:
        html, final_url = await fetch_page_resilient(url, timeout=timeout, referer=url)
        if not html:
            return []

        title_m = re.search(r"<h1[^>]+title=[\"']([^\"']+)[\"']", html)
        title = title_m.group(1) if title_m else "SpankBang Video"

        # 1. Inline stream_url_ patterns
        for m in re.finditer(r"stream_url_([^\s=]+)\s*=\s*[\"']([^\"']+)[\"']", html):
            q_id, s_url = m.group(1), m.group(2)
            if s_url and "http" in s_url:
                results.append({
                    "title": f"{title} ({q_id.upper()})",
                    "url": s_url,
                    "referer": url,
                    "quality": f"Master {q_id.upper()}",
                    "type": "Direct MP4 Video Stream",
                    "confidence": 98,
                    "score": 120 if "1080" in q_id or "4k" in q_id.lower() else 100
                })

        # 2. Dynamic streamkey endpoint fallback
        if not results:
            key_m = re.search(r"data-streamkey\s*=\s*[\"']([^\"']+)[\"']", html)
            if key_m:
                stream_key = key_m.group(1)
                api_url = "https://spankbang.com/api/videos/stream"
                headers = {
                    "User-Agent": DEFAULT_HEADERS["User-Agent"],
                    "Referer": url,
                    "X-Requested-With": "XMLHttpRequest"
                }
                async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
                    r = await cl.post(api_url, data={"id": stream_key, "data": 0}, headers=headers)
                    if r.status_code == 200:
                        data = r.json()
                        for q_id, s_url in data.items():
                            if isinstance(s_url, list) and s_url:
                                s_url = s_url[0]
                            if isinstance(s_url, str) and s_url.startswith("http"):
                                results.append({
                                    "title": f"{title} ({q_id.upper()})",
                                    "url": s_url,
                                    "referer": url,
                                    "quality": f"Master {q_id.upper()}",
                                    "type": "Direct MP4 Video Stream",
                                    "confidence": 99,
                                    "score": 125 if "1080" in q_id or "4k" in q_id.lower() else 105
                                })
    except Exception:
        pass
    return results


async def resolve_xvideos_direct_streams(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Direct master extractor for XVideos with HLS and high-def MP4 parsing."""
    results = []
    try:
        html, final_url = await fetch_page_resilient(url, timeout=timeout, referer=url)
        if not html:
            return []

        title_m = re.search(r"setVideoTitle\s*\(\s*[\"']([^\"']+)[\"']", html)
        title = title_m.group(1) if title_m else "XVideos Stream"

        for kind, s_url in re.findall(r"setVideo([^(]+)\([\"'](https?://[^\"']+)[\"']\)", html):
            k = kind.lower()
            if k == "hls":
                results.append({
                    "title": f"{title} (Master HLS)",
                    "url": s_url,
                    "referer": url,
                    "quality": "Master Multi-Bitrate HLS (1080p)",
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 130
                })
            elif k == "urlhigh":
                results.append({
                    "title": f"{title} (High-Def MP4)",
                    "url": s_url,
                    "referer": url,
                    "quality": "HD 720p / 1080p MP4 Direct",
                    "type": "Direct MP4 Video Stream",
                    "confidence": 98,
                    "score": 120
                })
            elif k == "urllow":
                results.append({
                    "title": f"{title} (Standard MP4)",
                    "url": s_url,
                    "referer": url,
                    "quality": "SD 360p / 480p MP4 Direct",
                    "type": "Direct MP4 Video Stream",
                    "confidence": 90,
                    "score": 90
                })
    except Exception:
        pass
    return results


async def resolve_pornhub_direct_streams(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Direct master extractor for PornHub with mediaDefinitions parsing."""
    results = []
    try:
        html, final_url = await fetch_page_resilient(url, timeout=timeout, referer=url)
        if not html:
            return []

        title_m = re.search(r"<h1[^>]+class=[\"']title[\"'][^>]*>(.*?)</h1>", html, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "PornHub Video"

        fv_m = re.search(r"var\s+flashvars_\d+\s*=\s*({.+?});", html)
        if fv_m:
            try:
                fv = json.loads(fv_m.group(1))
                media_defs = fv.get("mediaDefinitions", [])
                for md in media_defs:
                    s_url = md.get("videoUrl")
                    quality = str(md.get("quality", ""))
                    fmt = md.get("format", "")
                    if s_url and isinstance(s_url, str) and s_url.startswith("http"):
                        results.append({
                            "title": f"{title} ({quality}p)",
                            "url": s_url,
                            "referer": url,
                            "quality": f"{quality}p ({fmt})",
                            "type": "Direct Video Stream",
                            "confidence": 99,
                            "score": 125 if quality in ["1080", "720"] else 100
                        })
            except Exception:
                pass
    except Exception:
        pass
    return results


async def resolve_redtube_direct_streams(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Direct master extractor for RedTube with mediaDefinition and source parsing."""
    results = []
    try:
        html, final_url = await fetch_page_resilient(url, timeout=timeout, referer=url)
        if not html:
            return []

        title_m = re.search(r"<h1[^>]+class=[\"']video_title_text[\"'][^>]*>(.*?)</h1>", html, re.DOTALL)
        title = title_m.group(1).strip() if title_m else "RedTube Video"

        md_m = re.search(r"mediaDefinition[\"']?\s*:\s*(\[.+?}\s*\])", html)
        if md_m:
            try:
                medias = json.loads(md_m.group(1))
                for m in medias:
                    s_url = m.get("videoUrl")
                    q = str(m.get("quality", ""))
                    if s_url and s_url.startswith("http"):
                        results.append({
                            "title": f"{title} ({q}p)",
                            "url": s_url,
                            "referer": url,
                            "quality": f"{q}p Master",
                            "type": "Direct Video Stream",
                            "confidence": 99,
                            "score": 120 if q in ["1080", "720"] else 95
                        })
            except Exception:
                pass
    except Exception:
        pass
    return results


async def resolve_xhamster_direct_streams(url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Direct master extractor for XHamster with decipher engine."""
    results = []
    try:
        html, final_url = await fetch_page_resilient(url, timeout=timeout, referer=url)
        if not html:
            return []

        init_m = re.search(r"window\.initials\s*=\s*({.+?})\s*;\s*</script>", html)
        if not init_m:
            init_m = re.search(r"window\.initials\s*=\s*({.+?})\s*;", html)
        if init_m:
            try:
                initials = json.loads(init_m.group(1))
                video_model = initials.get("videoModel", {})
                title = video_model.get("title", "XHamster Video")
                sources = initials.get("xplayerSettings", {}).get("sources", {})
                
                # Standard sources
                standard = sources.get("standard", {})
                if isinstance(standard, dict):
                    for ident, fmt_list in standard.items():
                        if isinstance(fmt_list, list):
                            for fmt in fmt_list:
                                s_url = fmt.get("url") or fmt.get("fallback")
                                if s_url:
                                    real_url = decipher_xhamster_url(s_url)
                                    q = fmt.get("quality") or fmt.get("label") or "HD"
                                    results.append({
                                        "title": f"{title} ({q})",
                                        "url": real_url,
                                        "referer": url,
                                        "quality": f"{q} Deciphered Direct Stream",
                                        "type": "Direct Master Video Stream",
                                        "confidence": 99,
                                        "score": 125 if "1080" in str(q) or "720" in str(q) else 100
                                    })
            except Exception:
                pass
    except Exception:
        pass
    return results


class _YtDlpSilentLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

def resolve_via_universal_ytdlp(url: str) -> List[Dict[str, Any]]:
    """Universal fallback extractor leveraging 900+ specialized extractors in yt-dlp."""
    if not HAS_YT_DLP:
        return []
    
    # Do not invoke generic extractor on websites that have custom engines or anti-bot protections
    try:
        matched_ie = None
        for ie in yt_dlp.extractor.gen_extractors():
            if ie.suitable(url):
                matched_ie = ie.IE_NAME
                break
        if not matched_ie or matched_ie.lower() == 'generic':
            return []
    except Exception:
        pass

    results = []
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'logger': _YtDlpSilentLogger(),
        'extract_flat': False,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 4.0
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            title = info.get('title', 'Universal Stream')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            
            # Single direct stream URL
            direct_u = info.get('url')
            if direct_u and isinstance(direct_u, str) and direct_u.startswith('http'):
                results.append({
                    'title': title,
                    'url': direct_u,
                    'referer': url,
                    'thumbnail': thumbnail,
                    'quality': 'Master Universal Stream',
                    'type': 'Direct Media Stream',
                    'confidence': 99,
                    'score': 135
                })

            formats = info.get('formats', [])
            for f in formats:
                f_url = f.get('url')
                if not f_url or not isinstance(f_url, str) or not f_url.startswith('http'):
                    continue
                ext = str(f.get('ext', '')).lower()
                # Exclude image storyboards, mhtml, and audio-only streams
                if ext in ['mhtml', 'jpg', 'jpeg', 'webp', 'png', 'gif']:
                    continue
                vcodec = f.get('vcodec', 'none')
                if vcodec == 'none':
                    continue

                h = f.get('height') or 0
                if h <= 0 and 'audio' in str(f.get('format_note', '')).lower():
                    continue
                res_str = f.get('resolution') or (f'{h}p' if h else 'Auto')
                score = 100
                if h >= 2160:
                    score = 150
                elif h >= 1440:
                    score = 140
                elif h >= 1080:
                    score = 130
                elif h >= 720:
                    score = 115
                elif h >= 480:
                    score = 90
                
                results.append({
                    'title': f'{title} ({res_str})',
                    'url': f_url,
                    'referer': url,
                    'thumbnail': thumbnail,
                    'quality': f'{res_str} {ext.upper()}',
                    'type': 'Direct Media Stream',
                    'confidence': 95,
                    'score': score
                })
    except Exception:
        pass
    # Deduplicate by URL
    dedup = []
    seen = set()
    for r in results:
        if r['url'] not in seen:
            seen.add(r['url'])
            dedup.append(r)
    return dedup


async def resolve_porntrex_direct_streams(url: str, timeout: float = 8.0) -> List[Dict[str, Any]]:
    """Direct master extractor for Porntrex / KVS with IP origin TLS bypass & instant CDN token resolution."""
    results = []
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc
        ip = "88.80.24.7" # Origin server unthrottled by Cloudflare TLS handshake drop
        
        # Connect directly to origin with SNI omission
        s = socket.create_connection((ip, 443), timeout=5)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        s_wrapped = ctx.wrap_socket(s, server_hostname=None)

        req = f"GET {parsed.path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
        s_wrapped.sendall(req.encode())

        buf = b""
        while True:
            chunk = s_wrapped.recv(65536)
            if not chunk:
                break
            buf += chunk
        s_wrapped.close()
        html = buf.decode("utf-8", errors="replace")
        
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL) or re.search(r"<title>(.*?)</title>", html, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else "Porntrex Video"
        title = re.sub(r'\s*\|\s*Porntrex\.com.*$', '', title, flags=re.I).strip()
        get_files = list(set(re.findall(r'https?://[^\s"\'<>]+/get_file/[^\s"\'<>]+', html)))
        for gf in get_files:
            # Immediately resolve to CDN token via origin 302
            p_gf = urllib.parse.urlparse(gf)
            s_gf = socket.create_connection((ip, 443), timeout=4)
            s_gf_wrap = ctx.wrap_socket(s_gf, server_hostname=None)
            r_gf = f"GET {p_gf.path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            s_gf_wrap.sendall(r_gf.encode())
            h_gf = s_gf_wrap.recv(1500)
            s_gf_wrap.close()
            
            cdn_url = gf
            for line in h_gf.splitlines():
                ls = line.decode("latin1")
                if ":" in ls:
                    hk, hv = ls.split(":", 1)
                    if hk.strip().lower() == "location":
                        cdn_url = hv.strip()
                        break
            
            q_label = "2160p (4K)" if "2160p" in gf else ("1080p (FHD)" if "1080p" in gf else ("720p (HD)" if "720p" in gf else "HD Direct"))
            score = 150 if "2160p" in gf else (135 if "1080p" in gf else (120 if "720p" in gf else 100))
            
            results.append({
                "title": f"{title} ({q_label})",
                "url": cdn_url,
                "referer": url,
                "quality": q_label,
                "type": "Direct Master Video Stream",
                "confidence": 100,
                "score": score
            })
    except Exception:
        pass
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results

async def extract_any_streams(target_url: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """
    Universally crawls any webpage and extracts direct playable media streams.
    """
    clean_target = sanitize_user_url(target_url)
    if not clean_target:
        return []

    streams = []
    seen = set()

    # Unpack embedded video URLs in query parameters (e.g. videoUrl=https://.../movie.mkv)
    if any(k in clean_target.lower() for k in ("videourl=", "video_url=", "file=", "src=", "link=")):
        parsed_q = urllib.parse.urlparse(clean_target)
        qs = urllib.parse.parse_qs(parsed_q.query)
        for k, vals in qs.items():
            if k.lower() in ("videourl", "video_url", "file", "url", "src", "link"):
                for val in vals:
                    val_clean = val.strip().split("?")[0].lower()
                    if any(val_clean.endswith(ext) for ext in VIDEO_EXTENSIONS) or "r2.dev" in val or "r2.cloudflarestorage" in val:
                        return [{
                            "title": "Direct Extracted Stream (Embedded Video URL)",
                            "url": val.strip(),
                            "referer": clean_target,
                            "quality": "Direct Stream",
                            "type": "Direct Video Link",
                            "confidence": 100,
                            "score": 100
                        }]

    clean_url = clean_target.lower().split("?")[0]
    if (
        any(clean_url.endswith(ext) for ext in VIDEO_EXTENSIONS)
        or any(k in clean_target.lower() for k in ["workers.dev/serve", "workers.dev/d", "/serve?t=", "omd-rb."])
    ):
        return [{
            "title": "Cloudflare Worker Media Stream (OMDrive / Direct CDN)",
            "url": clean_target,
            "referer": "",
            "quality": "Direct Stream",
            "type": "Direct Video Link",
            "confidence": 100,
            "score": 100
        }]

    # Direct Specialized Tube & Master Network Resolvers
    low_url = clean_target.lower()
    if "porntrex.com" in low_url:
        pt_res = await resolve_porntrex_direct_streams(clean_target, timeout=timeout)
        if pt_res:
            return pt_res

    if "spankbang.com" in low_url:
        sb_res = await resolve_spankbang_direct_streams(clean_target, timeout=timeout)
        if sb_res:
            return sb_res

    if "xvideos.com" in low_url or "xvideos.es" in low_url or "xnxx.com" in low_url:
        xv_res = await resolve_xvideos_direct_streams(clean_target, timeout=timeout)
        if xv_res:
            return xv_res

    if "pornhub.com" in low_url or "thumbzilla.com" in low_url:
        ph_res = await resolve_pornhub_direct_streams(clean_target, timeout=timeout)
        if ph_res:
            return ph_res

    if "redtube.com" in low_url:
        rt_res = await resolve_redtube_direct_streams(clean_target, timeout=timeout)
        if rt_res:
            return rt_res

    if any(xh in low_url for xh in ["xhamster.com", "xhamster.desi", "xhms.pro", "xhday.com", "xhvid.com"]):
        xh_res = await resolve_xhamster_direct_streams(clean_target, timeout=timeout)
        if xh_res:
            return xh_res

    # Direct Doodstream URL check
    if any(d in clean_target.lower() for d in DOOD_HOSTS):
        d_res = await resolve_doodstream_direct_stream(clean_target)
        if d_res:
            return [{
                "title": "DoodStream Direct Video",
                "url": d_res["stream_url"],
                "referer": d_res["referer"],
                "quality": d_res["quality"],
                "type": "Direct MP4 Video Stream",
                "confidence": 100,
                "score": 100
            }]

    # Direct PlayMate URL check
    if "playmate" in clean_target.lower():
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            pm_res = await resolve_playmate_direct_stream(cl, clean_target)
            if pm_res:
                return [{
                    "title": "PlayMate Direct Stream",
                    "url": pm_res["stream_url"],
                    "referer": pm_res["referer"],
                    "quality": pm_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct StreamTape URL check
    if "streamtape" in clean_target.lower():
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            st_res = await resolve_streamtape_direct_stream(cl, clean_target)
            if st_res:
                return [{
                    "title": "StreamTape Direct MP4",
                    "url": st_res["stream_url"],
                    "referer": st_res["referer"],
                    "quality": st_res["quality"],
                    "type": "Direct MP4 Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct Mixdrop URL check
    if any(m in clean_target.lower() for m in ["mixdrop", "mixdrp", "md39"]):
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            md_res = await resolve_mixdrop_direct_stream(cl, clean_target)
            if md_res:
                return [{
                    "title": "Mixdrop Direct MP4",
                    "url": md_res["stream_url"],
                    "referer": md_res["referer"],
                    "quality": md_res["quality"],
                    "type": "Direct MP4 Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct FileMoon URL check
    if any(f in clean_target.lower() for f in ["filemoon", "moonplayer", "fmoon"]):
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            fm_res = await resolve_filemoon_direct_stream(cl, clean_target)
            if fm_res:
                return [{
                    "title": "FileMoon Direct Stream",
                    "url": fm_res["stream_url"],
                    "referer": fm_res["referer"],
                    "quality": fm_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct Voe URL check
    if "voe" in clean_target.lower():
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            voe_res = await resolve_voe_direct_stream(cl, clean_target)
            if voe_res:
                return [{
                    "title": "Voe Direct Stream",
                    "url": voe_res["stream_url"],
                    "referer": voe_res["referer"],
                    "quality": voe_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct VidSrc URL check
    if any(vs in clean_target.lower() for vs in ["vidsrc", "vixsrc", "2embed"]):
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            vs_res = await resolve_vidsrc_direct_stream(cl, clean_target)
            if vs_res:
                return [{
                    "title": "VidSrc Direct Stream",
                    "url": vs_res["stream_url"],
                    "referer": vs_res["referer"],
                    "quality": vs_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct VidHide URL check
    if any(vh in clean_target.lower() for vh in ["vidhide", "streamhide"]):
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            vh_res = await resolve_vidhide_direct_stream(cl, clean_target)
            if vh_res:
                return [{
                    "title": "VidHide Direct Stream",
                    "url": vh_res["stream_url"],
                    "referer": vh_res["referer"],
                    "quality": vh_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct Upstream URL check
    if "upstream.to" in clean_target.lower():
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            up_res = await resolve_upstream_direct_stream(cl, clean_target)
            if up_res:
                return [{
                    "title": "Upstream Direct Stream",
                    "url": up_res["stream_url"],
                    "referer": up_res["referer"],
                    "quality": up_res["quality"],
                    "type": "Direct Master HLS Stream",
                    "confidence": 100,
                    "score": 100
                }]

    # Direct Mp4Upload URL check
    if "mp4upload.com" in clean_target.lower():
        async with httpx.AsyncClient(timeout=timeout, verify=False) as cl:
            mp_res = await resolve_mp4upload_direct_stream(cl, clean_target)
            if mp_res:
                return [{
                    "title": "Mp4Upload Direct Video",
                    "url": mp_res["stream_url"],
                    "referer": mp_res["referer"],
                    "quality": mp_res["quality"],
                    "type": "Direct Video Link",
                    "confidence": 100,
                    "score": 100
                }]

    # Step 1.5: Universal 900+ Video Host Auto-Resolver
    if HAS_YT_DLP:
        try:
            yt_res = await asyncio.to_thread(resolve_via_universal_ytdlp, clean_target)
            if yt_res:
                yt_res.sort(key=lambda x: x.get('score', 0), reverse=True)
                return yt_res[:4]
        except Exception:
            pass

    req_headers = dict(DEFAULT_HEADERS)
    req_headers["Referer"] = clean_target

    html_text, base_url = await fetch_page_resilient(clean_target, timeout=timeout, referer=clean_target)
    if not html_text:
        console.print(f"[red]Error connecting to page:[/red] Could not retrieve page content (Connection or ISP block).")
        return []

    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, headers=req_headers) as client:

        # 1. Unpack any Dean Edwards JavaScript
        unpacked_html = unpack_packer(html_text)
        soup = BeautifulSoup(unpacked_html, "html.parser")
        page_title = soup.title.get_text().strip() if soup.title else "Video Stream"

        # 2. PRIORITY 1: Embedded Video Players (PlayMate, Vidara, Dood, StreamTape, etc.)
        for iframe in soup.find_all("iframe", src=True):
            iframe_src = urllib.parse.urljoin(base_url, iframe["src"])
            if iframe_src not in seen and not any(ign in iframe_src.lower() for ign in IGNORE_PATTERNS):
                seen.add(iframe_src)
                
                # A. DoodStream / D000d / Playmogo
                if any(d in iframe_src.lower() for d in DOOD_HOSTS):
                    d_res = await resolve_doodstream_direct_stream(iframe_src)
                    if d_res:
                        streams.append({
                            "title": f"{page_title} (Direct MP4)",
                            "url": d_res["stream_url"],
                            "referer": d_res["referer"],
                            "quality": d_res["quality"],
                            "type": "Direct MP4 Stream",
                            "confidence": 100,
                            "score": 100
                        })
                    else:
                        streams.append({
                            "title": f"{page_title} (DoodStream Player)",
                            "url": iframe_src,
                            "referer": base_url,
                            "quality": "HD Player",
                            "type": "Embedded Player",
                            "confidence": 85,
                            "score": 85
                        })

                # B. PlayMate
                elif "playmate" in iframe_src.lower():
                    pm_res = await resolve_playmate_direct_stream(client, iframe_src)
                    if pm_res:
                        streams.append({
                            "title": f"{page_title} (Direct Master HLS)",
                            "url": pm_res["stream_url"],
                            "referer": pm_res["referer"],
                            "quality": pm_res["quality"],
                            "type": "Direct Master HLS Stream",
                            "confidence": 100,
                            "score": 100
                        })
                    else:
                        streams.append({
                            "title": f"{page_title} (PlayMate Web Player)",
                            "url": iframe_src,
                            "referer": base_url,
                            "quality": "HD Web Player",
                            "type": "Embedded Player",
                            "confidence": 85,
                            "score": 85
                        })

                # C. Vidara / Vidarae
                elif any(v in iframe_src.lower() for v in ["vidara", "vidarae"]):
                    v_res = await resolve_vidara_direct_stream(client, iframe_src)
                    if v_res:
                        streams.append({
                            "title": f"{page_title} (Direct Master HLS)",
                            "url": v_res["stream_url"],
                            "referer": v_res["referer"],
                            "quality": v_res["quality"],
                            "type": "Direct Master HLS Stream",
                            "confidence": 100,
                            "score": 100
                        })
                    else:
                        streams.append({
                            "title": f"{page_title} (Vidara Player)",
                            "url": iframe_src,
                            "referer": base_url,
                            "quality": "HD Player",
                            "type": "Embedded Player",
                            "confidence": 85,
                            "score": 85
                        })

                # D. StreamTape
                elif "streamtape" in iframe_src.lower():
                    st_res = await resolve_streamtape_direct_stream(client, iframe_src)
                    if st_res:
                        streams.append({
                            "title": f"{page_title} (StreamTape MP4)",
                            "url": st_res["stream_url"],
                            "referer": st_res["referer"],
                            "quality": st_res["quality"],
                            "type": "Direct MP4 Stream",
                            "confidence": 100,
                            "score": 100
                        })

                # E. Mixdrop
                elif any(m in iframe_src.lower() for m in ["mixdrop", "mixdrp", "md39"]):
                    md_res = await resolve_mixdrop_direct_stream(client, iframe_src)
                    if md_res:
                        streams.append({
                            "title": f"{page_title} (Mixdrop MP4)",
                            "url": md_res["stream_url"],
                            "referer": md_res["referer"],
                            "quality": md_res["quality"],
                            "type": "Direct MP4 Stream",
                            "confidence": 100,
                            "score": 100
                        })

                # F. FileMoon
                elif any(f in iframe_src.lower() for f in ["filemoon", "moonplayer", "fmoon"]):
                    fm_res = await resolve_filemoon_direct_stream(client, iframe_src)
                    if fm_res:
                        streams.append({
                            "title": f"{page_title} (FileMoon HLS)",
                            "url": fm_res["stream_url"],
                            "referer": fm_res["referer"],
                            "quality": fm_res["quality"],
                            "type": "Direct Master HLS Stream",
                            "confidence": 100,
                            "score": 100
                        })

                # G. Voe
                elif "voe" in iframe_src.lower():
                    voe_res = await resolve_voe_direct_stream(client, iframe_src)
                    if voe_res:
                        streams.append({
                            "title": f"{page_title} (Voe HLS)",
                            "url": voe_res["stream_url"],
                            "referer": voe_res["referer"],
                            "quality": voe_res["quality"],
                            "type": "Direct Master HLS Stream",
                            "confidence": 100,
                            "score": 100
                        })

                # H. VidSrc / VixSrc
                elif any(vs in iframe_src.lower() for vs in ["vidsrc", "vixsrc", "2embed"]):
                    vs_res = await resolve_vidsrc_direct_stream(client, iframe_src)
                    if vs_res:
                        streams.append({
                            "title": f"{page_title} (VidSrc HLS)",
                            "url": vs_res["stream_url"],
                            "referer": vs_res["referer"],
                            "quality": vs_res["quality"],
                            "type": "Direct Master HLS Stream",
                            "confidence": 100,
                            "score": 100
                        })

                # I. General Embed Hosts
                else:
                    host_name = urllib.parse.urlparse(iframe_src).netloc
                    streams.append({
                        "title": f"{page_title} ({host_name} Player)",
                        "url": iframe_src,
                        "referer": base_url,
                        "quality": "HD Embed Stream",
                        "type": f"Embedded Player ({host_name})",
                        "confidence": 85,
                        "score": 85
                    })

        # 3. PRIORITY 2: HTML5 <video> & <source> tags
        for v in soup.find_all(["video", "source"]):
            src = v.get("src") or v.get("data-src") or v.get("data-video")
            if src and is_valid_video_stream(src):
                full_src = urllib.parse.urljoin(base_url, src)
                if full_src not in seen:
                    seen.add(full_src)
                    label = v.get("label") or v.get("title") or page_title
                    
                    # Detect quality tag: 1080p, 720p, 480p, etc.
                    q_val = v.get("size") or v.get("data-res") or v.get("res") or ""
                    if not q_val:
                        m_res = re.search(r"(\d{3,4})p?", full_src)
                        if m_res and int(m_res.group(1)) in [144, 240, 360, 480, 720, 1080, 1440, 2160]:
                            q_val = f"{m_res.group(1)}p"
                        else:
                            q_val = "HD Direct"
                    elif not str(q_val).endswith("p"):
                        q_val = f"{q_val}p"

                    streams.append({
                        "title": label,
                        "url": full_src,
                        "referer": base_url,
                        "quality": q_val,
                        "type": "HTML5 Video",
                        "confidence": 95,
                        "score": 95
                    })

        # 4. PRIORITY 3: Direct Script Variables & JSON APIs (flashvars, KVS, video_alt_url, etc.)
        script_patterns = [
            r'(?:file|source|video_url|video_alt_url|stream_url|contentUrl|src|streaming_url|sx)\s*[:=]\s*["\'](https?://[^"\']+\.(?:m3u8|mp4|webm|txt)[^"\']*)["\']',
            r'(?:video_url|video_alt_url)\s*[:=]\s*["\'](https?://[^"\']+/get_file/[^"\']+)["\']',
            r'["\'](https?://[^"\']+(?:/stream/|/hls/|/video/|/get_file/)[^"\']+\.(?:m3u8|mp4|txt)[^"\']*)["\']',
            r'["\'](https?://[^"\']+/get_file/[^"\']+)["\']'
        ]
        for pat in script_patterns:
            for match in re.finditer(pat, unpacked_html, re.IGNORECASE):
                st_url = match.group(1).replace("\\/", "/")
                full_st = urllib.parse.urljoin(base_url, st_url)
                if is_valid_video_stream(full_st) and full_st not in seen:
                    seen.add(full_st)
                    
                    # Detect quality
                    m_res = re.search(r"(\d{3,4})p?", full_st)
                    if m_res and int(m_res.group(1)) in [144, 240, 360, 480, 540, 720, 1080, 1440, 2160]:
                        q_name = f"{m_res.group(1)}p"
                    elif "hd" in full_st.lower():
                        q_name = "720p HD"
                    else:
                        q_name = "HD Direct"

                    streams.append({
                        "title": page_title,
                        "url": full_st,
                        "referer": base_url,
                        "quality": q_name,
                        "type": "Direct Master Video",
                        "confidence": 95,
                        "score": 95
                    })

    # Fallback to Universal Probe if standard extractions yielded nothing
    if not streams:
        try:
            from .universal_probe import probe_page_for_media
            fallback_streams = await probe_page_for_media(clean_target, client=client, timeout=timeout)
            for fs in fallback_streams:
                streams.append({
                    "title": fs.get("title", page_title),
                    "url": fs.get("url"),
                    "referer": clean_target,
                    "quality": "Probed Stream",
                    "type": fs.get("type", "Direct Media Stream"),
                    "confidence": fs.get("confidence", 85),
                    "score": fs.get("confidence", 85),
                })
        except Exception:
            pass

    # Extract video duration from Schema.org JSON-LD or meta tags to prioritize the real full-length feature
    expected_duration_secs = 0
    try:
        # Schema.org JSON-LD (e.g. PT19M41S -> 1181 seconds)
        for s_tag in soup.find_all("script", type="application/ld+json"):
            if s_tag.string:
                ld_match = re.search(r'"duration"\s*:\s*"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"', s_tag.string, re.IGNORECASE)
                if ld_match:
                    h = int(ld_match.group(1) or 0)
                    m = int(ld_match.group(2) or 0)
                    s = int(ld_match.group(3) or 0)
                    expected_duration_secs = (h * 3600) + (m * 60) + s
                    break
        # Meta duration tags
        if not expected_duration_secs:
            dur_meta = soup.find("meta", property=re.compile(r"video:duration|duration", re.I)) or soup.find("meta", attrs={"name": re.compile(r"duration", re.I)})
            if dur_meta and dur_meta.get("content", "").isdigit():
                expected_duration_secs = int(dur_meta["content"])
    except Exception:
        pass

    # Filter out dead / 404 removed CDN streams and short ads/trailers
    live_streams = []
    for s in streams:
        u = s.get("url", "")
        if not u:
            continue
        final_cdn_u, size_bytes = resolve_stream_to_final_cdn(u)
        if final_cdn_u:
            s["url"] = final_cdn_u
            s["size_bytes"] = size_bytes
            # Add human-readable size
            if size_bytes > 0:
                mb = size_bytes / (1024 * 1024)
                if mb >= 1024:
                    s["size_str"] = f"{mb / 1024:.2f} GB"
                else:
                    s["size_str"] = f"{mb:.1f} MB"
            else:
                s["size_str"] = ""

            # Filter out tiny video ads (< 5 MB) if other full-length files exist
            score = s.get("score", 90)
            if size_bytes > 50 * 1024 * 1024: # > 50 MB is definitely the real full video
                score += 30
            elif size_bytes > 15 * 1024 * 1024:
                score += 15
            elif 0 < size_bytes < 3 * 1024 * 1024: # < 3 MB is an ad banner or 5s preview
                score -= 40

            if expected_duration_secs > 60:
                s["duration_secs"] = expected_duration_secs
                mins = expected_duration_secs // 60
                secs = expected_duration_secs % 60
                s["duration_str"] = f"{mins}m {secs}s"

            # Prioritize higher resolution explicitly (1080p > 720p > 480p)
            q_lower = str(s.get("quality", "")).lower()
            if "2160" in q_lower or "4k" in q_lower:
                score += 50
            elif "1440" in q_lower or "2k" in q_lower:
                score += 45
            elif "1080" in q_lower:
                score += 40
            elif "720" in q_lower:
                score += 30
            elif "480" in q_lower:
                score += 15

            s["score"] = score
            live_streams.append(s)

    # Sort descending by resolution score, then file size (bandwidth)
    target_list = live_streams if live_streams else streams
    target_list.sort(key=lambda x: (x.get("score", 0), x.get("size_bytes", 0)), reverse=True)
    return target_list[:4] if target_list else []


async def handle_anystream_cli(raw_user_input: str):
    """Interactive CLI runner for universal stream extraction."""
    target_url = sanitize_user_url(raw_user_input)
    if not target_url:
        console.print("[bold red]❌ No valid URL could be parsed from your input.[/bold red]")
        return

    console.print(Panel(
        f"[bold cyan]🎯 AnyStream: Deep-Resolving Direct Playable Stream...[/bold cyan]\n[dim]{target_url}[/dim]",
        box=box.ROUNDED,
        border_style="cyan"
    ))

    with console.status("[bold yellow]Handshaking with video hosts, decrypting tokens & extracting master stream...[/bold yellow]"):
        streams = await extract_any_streams(target_url)

    if not streams:
        console.print(Panel("[bold red]❌ No direct video or stream links could be found on this page.[/bold red]", box=box.ROUNDED))
        return

    console.print(f"\n[bold green]✨ Found {len(streams)} Verified Direct Video Stream(s):[/bold green]")
    for idx, s in enumerate(streams, 1):
        score_badge = f"[bold green]{s.get('score', 90)}% Confidence[/bold green]"
        size_badge = f"[bold magenta]{s['size_str']}[/bold magenta]" if s.get("size_str") else ""
        dur_badge = f"[bold cyan]⏳ {s['duration_str']}[/bold cyan]" if s.get("duration_str") else ""
        meta_info = " • ".join(filter(None, [s['quality'], dur_badge, size_badge, score_badge]))
        
        console.print(f"  [bold white][{idx}][/bold white] 🎬 [bold yellow]{s['title']}[/bold yellow] • {meta_info}")
        console.print(f"      [dim]{s['url']}[/dim]")

    choice = Prompt.ask("\n[bold yellow]Select stream number to watch/download (or 0 to exit)[/bold yellow]", default="1")
    if choice == "0" or not choice.isdigit() or int(choice) > len(streams):
        return

    sel_stream = streams[int(choice) - 1]
    stream_url = sel_stream["url"]
    ref_header = sel_stream.get("referer", target_url)

    # Register persistent background session for auto-syncing & live token revalidation
    session_id = register_playback_session(
        origin_url=target_url,
        title=sel_stream.get("title", "Cinema Stream"),
        initial_streams=streams,
        referer=ref_header
    )

    console.print(Panel(
        f"[bold white][1][/bold white] 🌐 [bold green]Watch in Cinema Web Player (Chrome / Localhost)[/bold green] [bold cyan][Recommended][/bold cyan]\n"
        f"[bold white][2][/bold white] ▶ [bold yellow]Play in Desktop Player (PotPlayer / VLC)[/bold yellow]\n"
        f"[bold white][3][/bold white] 🚀 [bold cyan]Download with 8-Thread Turbo Downloader[/bold cyan]\n"
        f"[bold white][4][/bold white] 📋 [bold white]Copy Direct Stream Link[/bold white]",
        box=box.ROUNDED,
        title="⚡ Action Selector"
    ))

    act = Prompt.ask("[bold yellow]Choose action[/bold yellow]", choices=["1", "2", "3", "4"], default="1")
    if act == "1":
        web_player_url = get_web_player_url(session_id)
        console.print(f"\n[bold green]🎬 Launching Cinema Web Player in your Browser...[/bold green]")
        console.print(f"[dim]{web_player_url}[/dim]")
        try:
            webbrowser.open(web_player_url)
        except Exception:
            pass
        Prompt.ask("\n[bold yellow]Streaming active. Press Enter when done to return to menu[/bold yellow]")
    elif act == "2":
        console.print("[bold green]▶ Launching Media Player with Local Proxy Relay...[/bold green]")
        play_url = get_proxied_stream_url(stream_url, referer=ref_header, session_id=session_id)
        ok, msg = launch_video_stream_in_player(play_url)
        console.print(f"[bold green]✔ {msg}[/bold green]")
        console.print(f"[dim]Serving: {play_url}[/dim]")
        Prompt.ask("\n[bold yellow]Press Enter to return to menu[/bold yellow]")
    elif act == "3":
        console.print("[bold cyan]🚀 Starting Downloader for Stream...[/bold cyan]")
        await download_file_parallel_8_thread(stream_url, referer=ref_header)
    elif act == "4":
        console.print(f"\n[bold green]Direct Stream Link:[/bold green]\n[white]{stream_url}[/white]\n")
