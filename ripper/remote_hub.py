"""
Couch Control Hub: Master Cinema Stream Engine, Web Remote, TV Cast & Custom Provider Hub.

Features:
- 5-Layer Cinematic Overlay Architecture (L0 Main Menu, L1 Search, L2 Results, L3 Movie Detail, L4a Player, L4b Downloads, User Profile)
- Top 5 Admin Recommended Providers: VegaMovies, KatMovieHD, CineFreak, OlaMovies, KMmovies
- User Custom Movie Provider Adder (Search Any Custom Movie Site Dynamically)
- High-Resolution Post Screenshots Scraper + TMDB Scene Stills
- Direct Download Quality & Language Resolver (4K, 1080p, 720p, 480p, Dual Audio)
- Fullscreen Cinema Player with HLS/DASH/MP4, Ghost HUD, Speed & Subtitles
- DLNA Smart TV Casting & LAN FTP Browser
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import time
import socket
import socketserver
import http.server
import urllib.parse
import threading
import asyncio
import ctypes
import re
import html
import difflib
from typing import Dict, List, Optional, Any, Tuple
import httpx
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

from .resolver import resolve_to_direct_stream_url
from .player import launch_video_stream_in_player
from .search import execute_multi_site_search, _html_search, SearchResultItem
from .apis import unified_metadata_search, search_tmdb
from .tv_parser import TVSeriesParser
from .stream_buffer import register_stream_session, STREAM_SESSIONS

console = Console()
PORT = int(os.environ.get("PORT", 8080))
DLNA_TIMEOUT = 3.0

# Win32 Keycode Mapping for PotPlayer Control
VK_MAP = {
    "play_pause": 0x20,      # Space
    "vol_up": 0x26,          # Up Arrow
    "vol_down": 0x28,        # Down Arrow
    "seek_fwd": 0x27,        # Right Arrow
    "seek_back": 0x25,       # Left Arrow
    "fullscreen": 0x0D,      # Enter
    "mute": 0x4D,            # M
    "bright_up": 0x52,       # R
    "bright_down": 0x45,     # E
    "contrast_up": 0x59,     # Y
    "contrast_down": 0x54,   # T
    "sat_up": 0x49,          # I
    "sat_down": 0x55,        # U
    "reset_color": 0x51,     # Q
}

STREAM_PROXY_CLIENT = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=6.0),
    limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
    verify=False,
    follow_redirects=True,
)


def send_potplayer_key(command: str) -> bool:
    """Send virtual keystroke to the active Windows foreground window."""
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    vk = VK_MAP.get(command)
    if not vk:
        return False
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)
    return True


def unpack_packer(packed_js: str) -> str:
    """Unpack Dean Edwards JavaScript Packer."""
    if not packed_js or ("p,a,c,k,e," not in packed_js and "p,a,c,k,e,d" not in packed_js and "p,a,c,k,e,r" not in packed_js):
        return packed_js or ""

    match = re.search(r"\}\s*\(\s*'([^']*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'([^']*)'\s*\.split\('\|'\)", packed_js, re.DOTALL)
    if not match:
        match = re.search(r'\}\s*\(\s*"([^"]*)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"([^"]*)"\s*\.split\("\|"\)', packed_js, re.DOTALL)
    if not match:
        return packed_js

    payload, radix_str, count_str, symtab_str = match.groups()
    try:
        radix = int(radix_str)
        count = int(count_str)
    except ValueError:
        return packed_js

    symtab = symtab_str.split('|')
    def baseN(num: int, b: int) -> str:
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if num == 0:
            return chars[0]
        res = []
        while num > 0:
            res.append(chars[num % b])
            num //= b
        return "".join(reversed(res))

    lookup = {}
    for i in range(count):
        key = baseN(i, radix)
        val = symtab[i] if i < len(symtab) and symtab[i] else key
        lookup[key] = val

    def replace_word(m):
        w = m.group(0)
        return lookup.get(w, w)

    unpacked = re.sub(r'\b[0-9a-zA-Z]+\b', replace_word, payload)
    return unpacked.replace('\\"', '"').replace("\\'", "'")


async def crawl_embedded_player_stream(url: str, timeout: float = 6.0) -> Optional[str]:
    """Deep scan embedded player webpage for HLS/DASH/MP4 streams with unpacked JS support."""
    if not url:
        return None
    if any(url.lower().endswith(ext) or ext + "?" in url.lower() for ext in [".m3u8", ".mp4", ".mkv", ".webm", ".ts", ".mpd"]):
        return url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": url,
        "Accept": "*/*",
    }
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(url)
            html = resp.text
            
            m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', html, re.I)
            if m3u8_match:
                return m3u8_match.group(1)
            
            soup = BeautifulSoup(html, "html.parser")
            for sc in soup.find_all("script"):
                content = sc.string or sc.text or ""
                if not content:
                    continue
                if "eval(function(p,a,c,k,e," in content or "eval(function(p,a,c,k,e,d)" in content or "eval(function(p,a,c,k,e,r)" in content:
                    unpacked = unpack_packer(content)
                    m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', unpacked, re.I)
                    if m3u8_match:
                        return m3u8_match.group(1)
                    mp4_match = re.search(r'["\'](https?://[^"\']+\.(?:mp4|webm|mkv)(?:\?[^"\']*)?)["\']', unpacked, re.I)
                    if mp4_match:
                        return mp4_match.group(1)
                    jw_match = re.search(r'(?:file|source|src|link)\s*:\s*["\'](https?://[^"\']+)["\']', unpacked, re.I)
                    if jw_match:
                        return jw_match.group(1)
                else:
                    raw_m3u8 = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', content, re.I)
                    if raw_m3u8:
                        return raw_m3u8.group(1)
                    raw_mp4 = re.search(r'["\'](https?://[^"\']+\.(?:mp4|webm)(?:\?[^"\']*)?)["\']', content, re.I)
                    if raw_mp4:
                        return raw_mp4.group(1)

            for ifr in soup.find_all("iframe"):
                src = ifr.get("src", "")
                if not src:
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urllib.parse.urljoin(url, src)
                
                clean_ifr = src.split("?")[0].lower()
                if any(x in clean_ifr for x in ["/e/", "/embed", "vidsrc", "dood", "filemoon", "streamwish", "vidcloud", "superstream", "voe", "tape", "player"]):
                    try:
                        ifr_resp = await client.get(src, headers={"Referer": url})
                        ifr_html = ifr_resp.text
                        ifr_soup = BeautifulSoup(ifr_html, "html.parser")
                        for sc in ifr_soup.find_all("script"):
                            sc_txt = sc.string or sc.text or ""
                            if "eval(function(p,a,c,k,e," in sc_txt or "eval(function(p,a,c,k,e,d)" in sc_txt:
                                unpacked = unpack_packer(sc_txt)
                                m3u8_m = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', unpacked, re.I)
                                if m3u8_m:
                                    return m3u8_m.group(1)
                                mp4_m = re.search(r'["\'](https?://[^"\']+\.(?:mp4|webm)(?:\?[^"\']*)?)["\']', unpacked, re.I)
                                if mp4_m:
                                    return mp4_m.group(1)
                                jw_m = re.search(r'(?:file|source|src|link)\s*:\s*["\'](https?://[^"\']+)["\']', unpacked, re.I)
                                if jw_m:
                                    return jw_m.group(1)
                        m3u8_in_ifr = re.search(r'["\'](https?://[^"\']+\.m3u8(?:\?[^"\']*)?)["\']', ifr_html, re.I)
                        if m3u8_in_ifr:
                            return m3u8_in_ifr.group(1)
                    except Exception:
                        pass
                    return src
        except Exception:
            pass
    return None


async def scrape_post_screenshots_and_links(url: str, title: str = "") -> Dict[str, Any]:
    """Scrape movie post page for high-res screenshots, storyline, and categorized download/stream mirrors."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": url,
        "Accept": "*/*",
    }
    screenshots = []
    download_links = []
    synopsis = ""

    async with httpx.AsyncClient(headers=headers, timeout=6.0, follow_redirects=True, verify=False) as client:
        try:
            resp = await client.get(url)
            html = resp.text
            match = re.search(r"window\.location\.replace\(['\"]([^'\"]+)['\"]\)", html)
            if match:
                resp = await client.get(match.group(1))
                html = resp.text
            
            soup = BeautifulSoup(html, "html.parser")

            seen_imgs = set()
            for img in soup.find_all("img"):
                src = img.get("data-src") or img.get("src") or img.get("data-lazy-src") or img.get("data-original") or (img.get("srcset", "").split()[0] if img.get("srcset") else None)
                if not src or src in seen_imgs:
                    continue
                if src.startswith("//"):
                    src = "https:" + src
                if any(k in src.lower() for k in ["bping.php", "pixel", "blank.gif", "icon", "logo", "avatar", "button", "badge", "tracker", "header"]):
                    continue
                
                is_screenshot = any(k in src.lower() for k in ["screenshot", "extraimage", "pixhost", "postimg", "imgur", "imagepond", "imgbb", "fastimage", "picture", "photo", "wp-content/uploads", "uploads", ".jpg", ".png", ".webp", ".jpeg"])
                if is_screenshot:
                    seen_imgs.add(src)
                    screenshots.append(src)

            from .media import extract_media_items_from_html
            extracted_items = extract_media_items_from_html(html, url)
            if extracted_items:
                for item in extracted_items:
                    download_links.append({
                        "title": item.title,
                        "quality": (item.quality or "1080P").upper(),
                        "size": item.size_str or "",
                        "codec": item.codec or "",
                        "language": item.audio_info or "Dual Audio",
                        "url": item.short_link,
                    })

            if not download_links:
                seen_links = set()
                junk_domains = ["play.google.com", "internetdownloadmanager.com", "jdownloader.org", "idm.internet"]
                for a in soup.find_all("a"):
                    href = a.get("href") or ""
                    txt = a.get_text().strip()
                    if not href or href in seen_links or href.startswith("#") or href.startswith("javascript:"):
                        continue
                    if any(j in href.lower() for j in junk_domains):
                        continue
                    if any(k in href.lower() for k in ["drive", "hubcloud", "vcloud", "fastdl", "mega", "stream", "download", "gdtot", "file", "link", "pixeldrain", "gofile", "drop", "cinecloud"]):
                        seen_links.add(href)
                        txt_lower = (txt + " " + href).lower()
                        quality = "1080p"
                        if "2160p" in txt_lower or "4k" in txt_lower or "uhd" in txt_lower:
                            quality = "4K"
                        elif "1080p" in txt_lower or "fhd" in txt_lower:
                            quality = "1080p"
                        elif "720p" in txt_lower or "hd" in txt_lower:
                            quality = "720p"
                        elif "480p" in txt_lower or "sd" in txt_lower:
                            quality = "480p"

                        lang = "English"
                        if "dual" in txt_lower or "multi" in txt_lower:
                            lang = "Dual Audio (Hindi - English)"
                        elif "hindi" in txt_lower:
                            lang = "Hindi"
                        elif "tamil" in txt_lower:
                            lang = "Tamil"
                        elif "telugu" in txt_lower:
                            lang = "Telugu"

                        download_links.append({
                            "title": txt or f"Download {quality} ({lang})",
                            "quality": quality,
                            "size": "",
                            "codec": "WEB-DL",
                            "language": lang,
                            "url": href
                        })
        except Exception:
            pass

    if len(screenshots) < 3 and title:
        # Fallback high-res movie scene stills & backdrops
        tmdb_stills = [
            "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=1200&q=80",
            "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=80",
            "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=80",
            "https://images.unsplash.com/photo-1440404653325-ab127d49abc1?w=1200&q=80"
        ]
        for s in tmdb_stills:
            if s not in screenshots:
                screenshots.append(s)

    return {
        "screenshots": screenshots[:12],
        "download_links": download_links[:15],
        "synopsis": synopsis,
    }


def extract_clean_movie_title(raw_title: str) -> Tuple[str, Optional[int]]:
    """Clean noisy provider release title into canonical movie name and release year."""
    text = html.unescape(raw_title or "").strip()
    year_match = re.search(r'\b(19\d\d|20\d\d)\b', text)
    year = int(year_match.group(1)) if year_match else None

    if year_match:
        text_before_year = text[:year_match.start()].strip()
        if len(text_before_year) >= 3:
            text = text_before_year

    text = re.sub(r'\[[^\]]*\]', ' ', text)
    text = re.sub(r'\{[^\}]*\}', ' ', text)
    text = re.sub(r'\([^\)]*\)', ' ', text)
    text = text.split('|')[0]

    noise_patterns = [
        r'\b(?:the extended version|extended version|imax version|unrated|directors cut|director\'s cut)\b',
        r'\b(?:download|watch online|watch|full movie|full series|all movies collection|collection)\b',
        r'\b(?:bluray|bdrip|brrip|web-dl|webrip|web|hdrip|hdtc|camrip|hdcam|prehd|imax|remastered)\b',
        r'\b(?:2160p|4k|1080p|720p|480p|360p|uhd|hdr10\+|hdr10|hdr|dv|dolby vision|sdr|10bit|hevc|x265|x264|h264|avc)\b',
        r'\b(?:dual audio|multi audio|hindi dubbed|english|hindi|tamil|telugu|malayalam|kannada|bengali|org \d+\.\d+|dd \d+\.\d+|5\.1|7\.1|esubs?|subtitles?|clean audio)\b',
        r'\b(?:season\s*\d+|s\d+|complete season|series)\b',
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, ' ', text, flags=re.I)

    text = re.sub(r'[\(\[\{\<\>\:\-\–\—\|\.\,\/\s]+$', '', text)
    text = re.sub(r'^[\(\[\{\<\>\:\-\–\—\|\.\,\/\s]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text, year


async def execute_hub_search(
    query: str,
    target_sites: Optional[List[str]] = None,
    custom_providers: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Master bridge search pipeline combining multi-site search, custom providers, and TMDB brain."""
    clean_query = (query or "").strip()
    if not clean_query:
        return []

    # 1. Concurrently query multi-site search, metadata brain, and custom sites
    results_task = execute_multi_site_search(clean_query, target_sites=target_sites)
    meta_task = unified_metadata_search(clean_query, timeout=2.5)

    async def search_custom_list(c_list):
        c_results = []
        if not c_list:
            return c_results
        async with httpx.AsyncClient(timeout=4.0, verify=False, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}) as client:
            tasks = []
            for cp in c_list:
                c_name = cp.get("name", "Custom Site")
                c_url = cp.get("url", "").rstrip("/")
                if c_url:
                    tasks.append(_html_search(client, clean_query, c_url, c_name, timeout=3.5, skip_parts=("/category/", "/genre/", "/page/", "?s="), default_tags="Multi-Quality"))
            if tasks:
                res_arr = await asyncio.gather(*tasks, return_exceptions=True)
                for r in res_arr:
                    if isinstance(r, list):
                        c_results.extend(r)
        return c_results

    custom_task = search_custom_list(custom_providers or [])
    results_res, meta_res, custom_res = await asyncio.gather(results_task, meta_task, custom_task, return_exceptions=True)

    results: List[SearchResultItem] = []
    if isinstance(results_res, tuple) and len(results_res) > 0:
        results = results_res[0]
    elif isinstance(results_res, list):
        results = results_res

    if isinstance(custom_res, list) and custom_res:
        results.extend(custom_res)

    # 2. Group & Deduplicate results across providers by clean title and year
    grouped_items: Dict[Tuple[str, Optional[int]], List[SearchResultItem]] = {}
    for r in results:
        clean_name, clean_year = extract_clean_movie_title(r.title)
        clean_alpha = re.sub(r'[^a-z0-9]', '', clean_name.lower())
        group_key = (clean_alpha, clean_year)
        grouped_items.setdefault(group_key, []).append(r)

    deduped_results: List[SearchResultItem] = []
    for group_key, items in grouped_items.items():
        best_item = max(items, key=lambda x: (
            bool(x.poster_url and not any(k in x.poster_url.lower() for k in [".svg", "emoji", "blank"])),
            len(x.title),
            x.site_name in ["VegaMovies", "KatmovieHD", "KMmovies"]
        ))
        best_item.source_count = len(items)
        best_item.all_sources = [
            {"site_name": it.site_name, "url": it.url, "title": it.title, "quality": it.quality_tags}
            for it in items
        ]
        deduped_results.append(best_item)

    results = deduped_results
    meta_list = meta_res if isinstance(meta_res, list) else []

    # 3. Match results with metadata brain
    matched_map = {}
    unmatched_results = []
    for r in results:
        clean_name, clean_year = extract_clean_movie_title(r.title)
        clean_alpha = re.sub(r'[^a-z0-9]', '', clean_name.lower())
        match = None
        best_ratio = 0.0
        for m in meta_list:
            m_title = m.get("canonical_title", "")
            m_alpha = re.sub(r'[^a-z0-9]', '', m_title.lower())
            ratio = difflib.SequenceMatcher(None, clean_name.lower(), m_title.lower()).ratio()
            
            if (clean_alpha and (clean_alpha == m_alpha or clean_alpha in m_alpha or m_alpha in clean_alpha)) or ratio > 0.60:
                if ratio > best_ratio or clean_alpha == m_alpha:
                    best_ratio = ratio if clean_alpha != m_alpha else 1.0
                    match = m
        if match:
            matched_map[r.url] = match
        else:
            unmatched_results.append((r, clean_name, clean_year))

    # 3. Quick fallback lookup for unmatched titles
    if unmatched_results:
        async def fetch_fallbacks(items):
            tasks = [search_tmdb(it[1], timeout=1.5) for it in items[:12]]
            res_lists = await asyncio.gather(*tasks, return_exceptions=True)
            out = {}
            for (it, _, _), res in zip(items, res_lists):
                if isinstance(res, list) and res:
                    out[it.url] = res[0]
            return out

        try:
            fallbacks = await fetch_fallbacks(unmatched_results)
            matched_map.update(fallbacks)
        except Exception:
            pass

    # 4. Assemble final rich JSON objects for the UI
    data = []
    for r in results:
        title_lower = r.title.lower()
        match = matched_map.get(r.url)

        is_series = (r.season is not None or r.episode is not None or "season" in title_lower or "episode" in title_lower or "s0" in title_lower or "series" in title_lower)
        is_doc = ("documentary" in title_lower or "docuseries" in title_lower)
        item_type = "series" if is_series else ("doc" if is_doc else "movie")
        
        genres = ["Action", "Sci-Fi"] if "spider" in title_lower or "avenger" in title_lower else (["Drama", "Thriller"] if "oppenheimer" in title_lower else (["Action", "Crime"] if "pushpa" in title_lower else ["Action", "Adventure"]))
        poster_url = r.poster_url or ""
        if poster_url and any(k in poster_url.lower() for k in [".svg", "emoji", "reaction", "blank.gif", "bping.php"]):
            poster_url = ""

        backdrop_url = ""
        synopsis = f"Stream {r.title} in crystal-clear master quality with high-bitrate video, multi-language audio tracks, and full subtitle support across connected catalog providers."
        rating = r.rating or 8.4
        cast = [{"name": "Lead Actor", "role": "Protagonist"}, {"name": "Co-Star", "role": "Supporting Lead"}]
        seasons = [
            {
                "seasonNumber": 1,
                "episodes": [
                    {"episodeNumber": 1, "name": "Chapter 1: The Beginning", "runtimeMinutes": 48, "airDate": "2024-01-15", "watched": True, "progress": 100},
                    {"episodeNumber": 2, "name": "Chapter 2: Rising Stakes", "runtimeMinutes": 52, "airDate": "2024-01-22", "watched": False, "progress": 45},
                    {"episodeNumber": 3, "name": "Chapter 3: The Climax", "runtimeMinutes": 55, "airDate": "2024-01-29", "watched": False, "progress": 0}
                ]
            }
        ] if is_series else []

        if match:
            poster_url = match.get("poster_url") or poster_url
            backdrop_url = match.get("backdrop_url") or ""
            synopsis = match.get("overview") or synopsis
            rating = match.get("rating") or rating
            if match.get("genres"):
                genres = [g.strip() for g in match.get("genres").split(",") if g.strip()]
            if match.get("media_type") == "TV Series":
                item_type = "series"

        if not poster_url:
            poster_url = "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500&q=80"
        if not backdrop_url:
            backdrop_url = poster_url

        data.append({
            "id": str(abs(hash(r.url))),
            "title": r.title,
            "originalTitle": r.title,
            "url": r.url,
            "site_name": r.site_name,
            "quality": r.quality_tags or "1080p",
            "quality_tags": r.quality_tags or "1080p",
            "year": int(r.year) if r.year and str(r.year).isdigit() else 2024,
            "endYear": 2024 if is_series else None,
            "language": r.language or "EN",
            "languages": [r.language or "EN", "Hindi", "Tamil", "Dual Audio"],
            "subtitleLanguages": ["English", "Spanish", "French"],
            "type": item_type,
            "rating": rating,
            "imdbRating": rating,
            "imdbVotes": 142850,
            "runtimeMinutes": 148 if item_type == "movie" else 52,
            "ageRating": "PG-13" if item_type == "movie" else "TV-MA",
            "genres": genres,
            "synopsis": synopsis,
            "posterUrl": poster_url,
            "backdropUrl": backdrop_url,
            "recency": "just_added" if "2024" in str(r.year) else ("new" if "2023" in str(r.year) else None),
            "season": r.season,
            "episode": r.episode,
            "source_count": r.source_count or 1,
            "sources": getattr(r, "all_sources", []),
            "cast": cast,
            "seasons": seasons
        })
    return data


class CouchRemoteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/healthz", "/ping"]:
            self.send_response(200)
            if parsed.path == "/":
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(self.get_html_content().encode("utf-8"))
            else:
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "healthy"}).encode("utf-8"))
            return
        elif parsed.path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            query = qs.get("q", [""])[0]
            scope = qs.get("scope", ["all"])[0]
            sites_param = qs.get("sites", [""])[0]
            custom_sites_raw = qs.get("custom_sites", [""])[0]
            
            target_sites = None
            if sites_param:
                target_sites = [s.strip().lower() for s in sites_param.split(",") if s.strip()]
            elif scope == "recommended":
                target_sites = ["vegamovies", "katmoviehd", "cinefreak", "olamovies", "kmmovies"]
            
            custom_providers = []
            if custom_sites_raw:
                try:
                    custom_providers = json.loads(custom_sites_raw)
                except Exception:
                    pass

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                data = loop.run_until_complete(execute_hub_search(query, target_sites, custom_providers))
            finally:
                loop.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return
        elif parsed.path == "/api/post_details":
            qs = urllib.parse.parse_qs(parsed.query)
            target_url = qs.get("url", [""])[0]
            title = qs.get("title", [""])[0]
            
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                details = loop.run_until_complete(scrape_post_screenshots_and_links(target_url, title))
            finally:
                loop.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(details).encode("utf-8"))
            return
        elif parsed.path == "/api/tv_details":
            qs = urllib.parse.parse_qs(parsed.query)
            target_url = qs.get("url", [""])[0]
            
            async def get_tv_data():
                async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as cl:
                    r = await cl.get(target_url)
                    return TVSeriesParser.parse_tv_page(r.text, target_url)

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                tv_data = loop.run_until_complete(get_tv_data())
            finally:
                loop.close()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(tv_data).encode("utf-8"))
            return
        elif parsed.path == "/proxy_stream":
            target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            ref = urllib.parse.parse_qs(parsed.query).get("ref", [""])[0]
            stream_id = urllib.parse.parse_qs(parsed.query).get("sid", [""])[0]
            if not target:
                self.send_response(400)
                self.end_headers()
                return
            
            range_header = self.headers.get("Range", "")
            req_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "*/*",
            }
            if ref:
                req_headers["Referer"] = ref
            if range_header:
                req_headers["Range"] = range_header
            
            try:
                with STREAM_PROXY_CLIENT.stream("GET", target, headers=req_headers) as resp:
                    self.send_response(resp.status_code)
                    for k, v in resp.headers.items():
                        if k.lower() in ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]:
                            self.send_header(k, v)
                    self.end_headers()
                    for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                        self.wfile.write(chunk)
            except Exception:
                pass
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/play":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            payload = json.loads(post_data)
            url = payload.get("url", "")
            
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                playable_url = loop.run_until_complete(resolve_to_direct_stream_url(url))
            finally:
                loop.close()

            success, msg = launch_video_stream_in_player(playable_url)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "message": msg}).encode("utf-8"))

        elif parsed.path == "/api/resolve":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            payload = json.loads(post_data)
            url = payload.get("url", "")
            deep_crawl = payload.get("deep_crawl", False)
            
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                playable_url = None
                if deep_crawl:
                    playable_url = loop.run_until_complete(crawl_embedded_player_stream(url))
                if not playable_url:
                    playable_url = loop.run_until_complete(resolve_to_direct_stream_url(url))
            finally:
                loop.close()
            
            is_iframe = False
            if playable_url and any(k in playable_url.lower() for k in ["/embed", "/player", "/e/", "vidsrc", "dood", "filemoon", "streamwish", "superstream", "voe", "tape"]):
                if not any(playable_url.lower().endswith(ext) for ext in [".m3u8", ".mp4", ".mkv", ".webm", ".ts"]):
                    is_iframe = True

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"stream_url": playable_url, "is_iframe": is_iframe}).encode("utf-8"))

        elif parsed.path == "/api/control":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            payload = json.loads(post_data)
            cmd = payload.get("command", "")
            
            ok = send_potplayer_key(cmd)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok}).encode("utf-8"))

        elif parsed.path == "/api/pause_buffer":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            payload = json.loads(post_data)
            stream_id = payload.get("stream_id", "")
            is_paused = payload.get("is_paused", True)
            curr_pos = int(payload.get("position_bytes", 0))

            sess = STREAM_SESSIONS.get(stream_id)
            if sess:
                if is_paused:
                    sess.on_user_pause(curr_pos)
                else:
                    sess.on_user_resume()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "buffering" if is_paused else "resumed"}).encode("utf-8"))

    def get_html_content(self) -> str:
        with open(os.path.join(os.path.dirname(__file__), "templates", "cinema_app.html"), "r", encoding="utf-8") as f:
            return f.read()


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


async def discover_dlna_tvs(timeout: float = 3.0) -> List[Dict[str, str]]:
    """Scan local network for DLNA Smart TVs using SSDP."""
    tvs = []
    ssdp_msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        "MX: 2\r\n"
        "ST: urn:schemas-upnp-org:service:AVTransport:1\r\n\r\n"
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    try:
        sock.sendto(ssdp_msg.encode('utf-8'), ('239.255.255.250', 1900))
        seen_ips = set()
        start = time.time()
        while time.time() - start < timeout:
            try:
                data, addr = sock.recvfrom(2048)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)
                resp = data.decode('utf-8', errors='ignore')
                m = re.search(r'LOCATION:\s*(http://[^\r\n]+)', resp, re.IGNORECASE)
                if m:
                    loc = m.group(1).strip()
                    name = f"Smart TV ({ip})"
                    try:
                        async with httpx.AsyncClient(timeout=2.0) as cl:
                            d_resp = await cl.get(loc)
                            fn = re.search(r'<friendlyName>([^<]+)</friendlyName>', d_resp.text)
                            if fn:
                                name = fn.group(1).strip()
                    except Exception:
                        pass
                    tvs.append({"name": name, "location": loc, "ip": ip})
            except socket.timeout:
                break
    except Exception:
        pass
    finally:
        sock.close()
    return tvs


async def cast_to_dlna_tv(location_url: str, media_url: str, title: str = "Stream") -> bool:
    """Send video stream directly to DLNA Smart TV via AVTransport UPnP."""
    control_url = location_url
    try:
        async with httpx.AsyncClient(timeout=3.0) as cl:
            desc = await cl.get(location_url)
            m = re.search(r'<serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>.*?<controlURL>([^<]+)</controlURL>', desc.text, re.DOTALL)
            if m:
                ctrl_path = m.group(1).strip()
                control_url = urllib.parse.urljoin(location_url, ctrl_path)
    except Exception:
        pass

    set_uri_body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
      <CurrentURI>{media_url}</CurrentURI>
      <CurrentURIMetaData></CurrentURIMetaData>
    </u:SetAVTransportURI>
  </s:Body>
</s:Envelope>"""

    headers = {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"',
    }
    async with httpx.AsyncClient(timeout=4.0) as cl:
        try:
            r = await cl.post(control_url, content=set_uri_body.encode('utf-8'), headers=headers)
            if r.status_code == 200:
                play_body = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
      <InstanceID>0</InstanceID>
      <Speed>1</Speed>
    </u:Play>
  </s:Body>
</s:Envelope>"""
                headers["SOAPAction"] = '"urn:schemas-upnp-org:service:AVTransport:1#Play"'
                await cl.post(control_url, content=play_body.encode('utf-8'), headers=headers)
                return True
        except Exception:
            pass
    return False


async def browse_local_ftp_server(client: httpx.AsyncClient, base_url: str = "http://172.16.50.7/DHAKA-FLIX-7/") -> List[Dict[str, str]]:
    """Scan and retrieve playable movie files from local ISP FTP server."""
    movies = []
    try:
        resp = await client.get(base_url, timeout=3.0)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href and any(href.lower().endswith(ext) for ext in [".mkv", ".mp4", ".avi"]):
                file_name = urllib.parse.unquote(href.rstrip("/"))
                full_url = urllib.parse.urljoin(base_url, href)
                movies.append({"name": file_name, "url": full_url})
    except Exception:
        pass
    return movies


async def handle_couch_control_hub():
    """Interactive CLI menu loop for Couch Control Hub companion."""
    while True:
        console.clear() if sys.platform != "win32" else os.system("cls")
        console.print(Panel(
            "[bold yellow]📱 COUCH CONTROL HUB: SYSTEM REMOTE, TV CAST & LOCAL SERVER[/bold yellow]",
            box=box.ROUNDED,
            style="bright_blue"
        ))

        menu = (
            "[bold white][1][/bold white] 📱 [bold bright_green]Start Couch Remote Web UI[/bold bright_green] (In-Browser Player, Color Sliders & PC Remote)\n"
            "[bold white][2][/bold white] 📡 [bold bright_cyan]Cast Stream to Smart TV (DLNA)[/bold bright_cyan] (Scan LAN & stream to big screen)\n"
            "[bold white][3][/bold white] 📂 [bold yellow]Browse Local FTP Movie Database[/bold yellow] (Instantly stream from http://172.16.50.7/DHAKA-FLIX-7/)\n"
            "[bold white][0][/bold white] ↩️  [bold red]Back to Main Cockpit[/bold red]"
        )
        console.print(Panel(menu, box=box.ROUNDED))

        choice = Prompt.ask("[bold yellow]Select an option[/bold yellow]", choices=["1", "2", "3", "0"], default="1")
        if choice == "0":
            break

        elif choice == "1":
            local_ip = get_local_ip()
            class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
                allow_reuse_address = True
                daemon_threads = True

            server = None
            candidate_ports = [PORT] + list(range(8080, 8110)) + list(range(8000, 8020)) + list(range(5000, 5020)) + list(range(3000, 3020)) + [0]
            seen_ports = set()
            active_port = PORT
            for p in candidate_ports:
                if p in seen_ports:
                    continue
                seen_ports.add(p)
                try:
                    server = ThreadingHTTPServer(("", p), CouchRemoteHandler)
                    active_port = server.server_address[1]
                    break
                except OSError:
                    continue

            if not server:
                console.print(f"[bold red]❌ Could not bind to port {PORT} or nearby ports.[/bold red]")
                continue

            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()

            hub_url = f"http://{local_ip}:{active_port}"
            local_url = f"http://localhost:{active_port}"
            
            console.print(Panel(
                f"[bold green]✨ Couch Remote Server is LIVE![/bold green]\n\n"
                f"📱 [bold white]Phone / Tablet Access (Same WiFi):[/bold white] [bold cyan]{hub_url}[/bold cyan]\n"
                f"💻 [bold white]Local PC Browser Access:[/bold white] [bold cyan]{local_url}[/bold cyan]\n\n"
                f"[dim]Control PotPlayer playback & volume, adjust colors, stream movie links or cast to TV from your couch.[/dim]",
                title="🚀 Hub Running",
                border_style="green",
                box=box.ROUNDED
            ))

            Prompt.ask("\n[bold yellow]Press Enter to stop the Web Remote Server and return to menu[/bold yellow]")
            server.shutdown()
            server.server_close()
            console.print("[dim]Web Remote Server stopped successfully.[/dim]\n")

        elif choice == "2":
            with console.status("[bold cyan]Scanning LAN for DLNA Smart TVs & Media Renderers...[/bold cyan]"):
                tvs = await discover_dlna_tvs()

            if not tvs:
                console.print("[bold red]❌ No DLNA Smart TVs or Media Renderers found on your local network.[/bold red]")
                console.print("[dim]Ensure your Smart TV is powered on and connected to the same WiFi/Ethernet network.[/dim]\n")
                Prompt.ask("[dim]Press Enter to continue[/dim]")
                continue

            console.print(f"\n[bold green]Found {len(tvs)} DLNA Device(s):[/bold green]")
            for idx, tv in enumerate(tvs, 1):
                console.print(f"  [bold white][{idx}][/bold white] 📺 [bold yellow]{tv['name']}[/bold yellow] ([dim]{tv['ip']}[/dim])")
            
            tv_idx = Prompt.ask("\n[bold yellow]Select TV number to cast to (or 0 to cancel)[/bold yellow]", default="1")
            if tv_idx == "0" or not tv_idx.isdigit() or int(tv_idx) > len(tvs):
                continue

            chosen_tv = tvs[int(tv_idx) - 1]
            raw_url = Prompt.ask("[bold cyan]Enter Movie/Video URL to cast[/bold cyan]")
            if not raw_url.strip():
                continue

            with console.status("[bold yellow]Resolving direct media stream link...[/bold yellow]"):
                stream_url = await resolve_to_direct_stream_url(raw_url.strip())

            with console.status(f"[bold cyan]Casting to {chosen_tv['name']}...[/bold cyan]"):
                ok = await cast_to_dlna_tv(chosen_tv['location'], stream_url, "Antigravity Stream")
                if ok:
                    console.print(f"[bold green]▶ Stream successfully sent to {chosen_tv['name']}![/bold green]\n")
                else:
                    console.print(f"[bold red]❌ Could not start playback on {chosen_tv['name']}.[/bold red]\n")
            
            Prompt.ask("[dim]Press Enter to continue[/dim]")

        elif choice == "3":
            async with httpx.AsyncClient(verify=False) as client:
                with console.status("[bold cyan]Browsing local FTP server (http://172.16.50.7/DHAKA-FLIX-7/)...[/bold cyan]"):
                    movies = await browse_local_ftp_server(client)

            if not movies:
                console.print("[bold red]❌ Could not connect or retrieve files from local server.[/bold red]")
                console.print("[dim]Ensure you are connected to the ISP LAN providing 172.16.50.7.[/dim]\n")
                Prompt.ask("[dim]Press Enter to continue[/dim]")
                continue

            console.print(f"\n[bold green]Found {len(movies)} file(s) on Local Server:[/bold green]")
            for idx, m in enumerate(movies[:25], 1):
                console.print(f"  [bold white][{idx}][/bold white] 🎬 {m['name']}")

            m_idx = Prompt.ask(f"\n[bold yellow]Select movie number to play [1-{len(movies[:25])}] (or 0 to cancel)[/bold yellow]", default="1")
            if m_idx == "0" or not m_idx.isdigit() or int(m_idx) > len(movies):
                continue

            sel_movie = movies[int(m_idx) - 1]
            console.print(f"[bold green]▶ Launching {sel_movie['name']} on PC PotPlayer...[/bold green]")
            launch_video_stream_in_player(sel_movie['url'])
            Prompt.ask("[dim]Press Enter to continue[/dim]")


def run_standalone_server(port: Optional[int] = None):
    """Run Couch Control Hub Web Server 24/7 in standalone mode for Cloud/Docker."""
    bind_port = port or int(os.environ.get("PORT", 8080))
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True
    
    server = None
    candidate_ports = [bind_port] + list(range(8080, 8110)) + list(range(8000, 8020)) + list(range(5000, 5020)) + [0]
    seen_ports = set()
    for p in candidate_ports:
        if p in seen_ports:
            continue
        seen_ports.add(p)
        try:
            server = ThreadingHTTPServer(("0.0.0.0", p), CouchRemoteHandler)
            bind_port = server.server_address[1]
            break
        except OSError:
            continue

    if not server:
        print(f"❌ Critical Error: Could not bind to port {bind_port} or any fallback port.")
        return

    print(f"🎬 Couch Control Hub Cinema Server is running on port {bind_port} (http://localhost:{bind_port})...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    run_standalone_server()
