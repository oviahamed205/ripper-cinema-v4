"""
Structured Media, Episode & Quality Scraper Engine for unshorten-cli (Enterprise & Pro Edition).
Features:
- High-Speed Direct Stream Resolver (Under 1 second)
- Deterministic /d/<id> Direct Cloudflare R2 Stream Extraction
- Precision Season/Episode & Regional Language Extraction (Tamil, Telugu, Malayalam, etc.)
- Quality Ranking Score & Codec Priority Deduplication
- Auto-Detects URL vs HTML Input
- Precision container scoping (<div class="download-links-div">, <div class="episode-grid">)
"""

import re
import os
import asyncio
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Set
from bs4 import BeautifulSoup
import httpx

from .models import ServerMirror
from .resolver import (
    extract_url_from_query_params,
    crawl_intermediate_server_page,
    extract_server_options_from_html,
    extract_filename_from_url_or_headers,
)
from .resolver.core.honeypot_filter import is_ad_trap
from .downloader import sanitize_filename

# Quality & Codec regexes
QUALITY_REGEX = re.compile(r'\b(2160p|4k\s*uhd|4k|1080p|720p|480p|360p)\b', re.IGNORECASE)
CODEC_REGEX = re.compile(r'\b(remux|mvc|3d|h-sbs|h-ou|sbs|ou|60fps|120fps|144fps|hdr10\+\s*dv|hdr10\+|hdr10|hdr|dv|dolby\s*vision|sdr|bluray|bdrip|brrip|web-dl|webrip|hdtc|camrip|10bit|hevc|x265|h265|x264|h264|avc|hd|sd)\b', re.IGNORECASE)
AUDIO_REGEX = re.compile(
    r'\[\s*([^\]]*?(?:hindi|english|dual|audio|line|esub|sub|tamil|telugu|malayalam|kannada|bengali|bangla|marathi|punjabi|urdu|multi)[^\]]*?)\s*\]',
    re.IGNORECASE,
)
SIZE_REGEX = re.compile(r'(?:\[|\b)(\d+(?:\.\d+)?\s*(?:GB|MB|GiB|MiB|gb|mb|gib|mib))(?:\]|\b)', re.IGNORECASE)

SEASON_EP_REGEX = re.compile(
    r'\b(?:S|Season)\s*(\d{1,2})(?:\s*(?:E|Ep|Episode)\s*(\d{1,2}))?\b',
    re.IGNORECASE,
)

LANGUAGE_KEYWORDS = {
    "hindi": ["hindi", "hin", "hindi dubbed"],
    "english": ["english", "eng", "hollywood"],
    "tamil": ["tamil", "tam", "kollywood"],
    "telugu": ["telugu", "tel", "tollywood"],
    "malayalam": ["malayalam", "mal", "mollywood"],
    "kannada": ["kannada", "kan", "sandalwood"],
    "bengali": ["bengali", "ben", "bangla", "bangla dubbed"],
    "marathi": ["marathi", "mar"],
    "punjabi": ["punjabi", "pun"],
    "urdu": ["urdu", "pakistani"],
    "dual": ["dual audio", "dual"],
    "multi": ["multi audio", "multi-audio", "multilang"],
}

LANG_DISPLAY_MAP = {
    "hindi": "🇮🇳 Hindi",
    "english": "🇺🇸 English",
    "tamil": "🎬 Tamil",
    "telugu": "🎬 Telugu",
    "malayalam": "🎬 Malayalam",
    "kannada": "🎬 Kannada",
    "bengali": "🎬 Bengali",
    "marathi": "🎬 Marathi",
    "punjabi": "🎬 Punjabi",
    "urdu": "🎬 Urdu",
    "dual": "🔊 Dual Audio",
    "multi": "🔊 Multi Audio",
}

CODEC_PRIORITY = {
    "HEVC": 6,
    "X265": 6,
    "H265": 6,
    "10BIT": 5,
    "HDR": 5,
    "HDR10": 5,
    "DV": 5,
    "BLURAY": 4,
    "BDRIP": 4,
    "WEB-DL": 3,
    "WEBRIP": 2,
    "HDRIP": 1,
    "HD": 1,
    "HQ": 1,
    "HQ-LOW": 0,
    "SD": 0,
}

QUALITY_SCORE_WEIGHTS = {
    "direct_r2": 50,
    "direct_s3": 45,
    "pixeldrain": 40,
    "resumable": 20,
    "hevc": 15,
    "bluray": 12,
    "web_dl": 8,
    "landing_page": -10,
    "ad_wrapped": -20,
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class MediaDownloadItem:
    """Represents a clean, structured media download option."""
    title: str
    movie_name: str
    quality: str
    codec: str
    size_str: str
    audio_info: str
    short_link: str
    unshortened_landing_url: Optional[str] = None
    servers: List[ServerMirror] = field(default_factory=list)
    season: Optional[int] = None
    episode: Optional[int] = None
    language: Optional[str] = None


def detect_language(text: str) -> Optional[str]:
    """Detect primary language from title/header text based on first occurrence."""
    text_lower = text.lower()
    first_lang = None
    first_pos = 999999
    for lang, keywords in LANGUAGE_KEYWORDS.items():
        for kw in keywords:
            idx = text_lower.find(kw)
            if idx != -1 and idx < first_pos:
                first_pos = idx
                first_lang = lang.capitalize()
    return first_lang


def extract_season_episode(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract season and episode numbers from title text."""
    m = SEASON_EP_REGEX.search(text)
    if m:
        season = int(m.group(1))
        episode = int(m.group(2)) if m.group(2) else None
        return season, episode
    alt_m = re.search(r'(\d{1,2})(?:st|nd|rd|th)\s+season', text, re.I)
    if alt_m:
        return int(alt_m.group(1)), None
    return None, None


def get_codec_priority(codec_str: str) -> int:
    """Get priority score for codec string."""
    return CODEC_PRIORITY.get(codec_str.upper(), 0)


def calculate_quality_score(mirror: ServerMirror, codec: str, quality: str) -> float:
    """Compute ranking score for mirror based on directness, protocol and quality."""
    score = 0.0
    url_low = (mirror.direct_download_url or mirror.intermediate_url or "").lower()
    label_low = mirror.label.lower()

    if mirror.direct_download_url:
        if "r2.cloudflarestorage.com" in url_low:
            score += QUALITY_SCORE_WEIGHTS["direct_r2"]
        elif "amazonaws.com" in url_low:
            score += QUALITY_SCORE_WEIGHTS["direct_s3"]
        elif "pixeldrain" in url_low:
            score += QUALITY_SCORE_WEIGHTS["pixeldrain"]
        else:
            score += 35
    else:
        score += QUALITY_SCORE_WEIGHTS["landing_page"]

    if mirror.is_resumable:
        score += QUALITY_SCORE_WEIGHTS["resumable"]

    c_upper = codec.upper()
    if "HEVC" in c_upper or "X265" in c_upper or "10BIT" in c_upper:
        score += QUALITY_SCORE_WEIGHTS["hevc"]
    if "BLURAY" in c_upper:
        score += QUALITY_SCORE_WEIGHTS["bluray"]
    elif "WEB-DL" in c_upper:
        score += QUALITY_SCORE_WEIGHTS["web_dl"]

    if "fast" in label_low or "cloud" in label_low:
        score += 10
    if "hubcloud" in label_low or "kmhd" in label_low:
        score += 15

    return score


def clean_cinecloud_url(url: str) -> str:
    """Remove trailing site signature tokens (like newgo32) from cinecloud URLs."""
    return re.sub(r'(/f/[a-f0-9]{8})[a-zA-Z0-9_]+$', r'\1', url)


def parse_movie_title_header(header_text: str) -> Tuple[str, str, str, str, str, Optional[int], Optional[int]]:
    """Parse title and button text into (movie_name, audio, codec, quality, size, season, episode)."""
    clean_line = " ".join(header_text.split())

    size_m = SIZE_REGEX.search(clean_line)
    size_str = size_m.group(1).strip() if size_m else "Unknown"

    audio_m = AUDIO_REGEX.search(clean_line)
    audio_str = audio_m.group(1).strip() if audio_m else "Hindi & English"

    q_m = QUALITY_REGEX.search(clean_line)
    quality = q_m.group(1).upper() if q_m else "1080P"

    # Extract all rich print & codec features
    features = []
    if re.search(r'\b(?:remux)\b', clean_line, re.I):
        features.append('REMUX')
    if re.search(r'\b(?:mvc)\b', clean_line, re.I):
        features.append('MVC')
    if re.search(r'\{?3d\}?', clean_line, re.I):
        features.append('3D')
    if re.search(r'\{?(?:h-sbs|sbs)\}?', clean_line, re.I):
        features.append('H-SBS')
    if re.search(r'\{?(?:h-ou|ou)\}?', clean_line, re.I):
        features.append('H-OU')
    if re.search(r'\b(?:hdr10\+\s*dv|hdr10\+|hdr10|hdr|dv|dolby\s*vision)\b', clean_line, re.I):
        m = re.search(r'\b(hdr10\+\s*dv|hdr10\+|hdr10|hdr|dv|dolby\s*vision)\b', clean_line, re.I)
        features.append(m.group(1).upper())
    if re.search(r'\b(?:sdr)\b', clean_line, re.I):
        features.append('SDR')
    if re.search(r'\b(\d+fps)\b', clean_line, re.I):
        features.append(re.search(r'\b(\d+fps)\b', clean_line, re.I).group(1).upper())
    if re.search(r'\b(bluray|bdrip|brrip|web-dl|webrip|hdtc|camrip)\b', clean_line, re.I):
        features.append(re.search(r'\b(bluray|bdrip|brrip|web-dl|webrip|hdtc|camrip)\b', clean_line, re.I).group(1).upper())
    if re.search(r'\b(hq-low|hq|sd)\b', clean_line, re.I):
        m = re.search(r'\b(hq-low|hq|sd)\b', clean_line, re.I)
        c_tag = m.group(1).upper()
        if c_tag not in features:
            features.append(c_tag)
    if re.search(r'\b(10bit|hevc|x265|x264|h264|avc)\b', clean_line, re.I):
        for cm in re.finditer(r'\b(10bit|hevc|x265|x264|h264|avc)\b', clean_line, re.I):
            c_tag = cm.group(1).upper()
            if c_tag not in features:
                features.append(c_tag)

    codec = " ".join(features) if features else ("HD" if "HD" in clean_line.upper() else "HD")

    if "[" in clean_line:
        movie_name = clean_line.split("[")[0].strip()
    else:
        movie_name = clean_line[:40]

    season, episode = extract_season_episode(clean_line)
    return movie_name, audio_str, codec, quality, size_str, season, episode


def extract_media_items_from_html(html_content: str, base_url: str) -> List[MediaDownloadItem]:
    """
    Precision extraction targeting download containers and link sections across all supported providers:
    CineFreak, VegaMovies, KMmovies, KatmovieHD, HDHub4u, BollyFlix, etc.
    Drops irrelevant links (categories, home, imdb, youtube, watch online).
    """
    soup = BeautifulSoup(html_content, "html.parser")
    raw_items: List[MediaDownloadItem] = []
    seen_links: Set[str] = set()

    # Extract clean default movie name from post title
    movie_title_tag = soup.find("h1") or soup.find("title")
    default_mtitle = movie_title_tag.get_text().strip() if movie_title_tag else "Movie"
    default_mname = re.sub(r'^(?:Download|Watch)\s+', '', default_mtitle, flags=re.I).split(" | ")[0].split(" - ")[0].strip()

    # Pass 1: Structured download containers or article-wide heading groups
    dl_containers = soup.find_all(class_=re.compile(r"download-links-div|episode-grid|download-links", re.I))
    header_groups = []
    if dl_containers:
        for container in dl_containers:
            title_headers = container.find_all(re.compile(r"h[2-5]"), class_=re.compile(r"movie-title|title|quality", re.I))
            if not title_headers:
                title_headers = container.find_all(["h3", "h4", "h5"])
            if title_headers:
                header_groups.extend(title_headers)
    else:
        # Article-wide structured headings (VegaMovies, KatMovieHD, BollyFlix, HDHub4u, etc.)
        for h in soup.find_all(re.compile(r"^h[2-6]$", re.I)):
            h_text = h.get_text(separator=" ").strip()
            if QUALITY_REGEX.search(h_text) or SIZE_REGEX.search(h_text):
                header_groups.append(h)

    if header_groups:
        for h in header_groups:
            header_text = h.get_text(separator=" ").strip()
            if "uploading soon" in header_text.lower():
                continue

            movie_name, audio, codec, quality, size_str, season, episode = parse_movie_title_header(header_text)
            lang = detect_language(header_text)

            # Collect links: check direct sibling elements until next header
            links = []
            curr = h.next_sibling
            while curr:
                if hasattr(curr, "name") and curr.name and re.match(r"^h[1-6]$", curr.name, re.I):
                    break
                if hasattr(curr, "name") and curr.name == "a":
                    links.append(curr)
                elif hasattr(curr, "find_all"):
                    links.extend(curr.find_all("a"))
                curr = curr.next_sibling

            for a in links:
                href = a.get("href") or ""
                text = a.get_text().strip()
                classes = " ".join(a.get("class", [])).lower()

                if "dlbtn-watch" in classes or "watch online" in text.lower() or "/x/" in href:
                    continue
                if not href or href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
                    continue
                if any(bad in href.lower() for bad in ["imdb.com", "youtube.com", "category/", "tag/", "genre/", "#comment", "#respond"]):
                    continue

                full_url = urllib.parse.urljoin(base_url, href)
                if full_url in seen_links or is_ad_trap(full_url) or "vglist" in full_url.lower() or "vegamovies-apk" in full_url.lower():
                    continue

                # Filter internal article / recommended post URLs on same domain
                base_host = urllib.parse.urlparse(base_url).netloc.lower()
                full_host = urllib.parse.urlparse(full_url).netloc.lower()
                if base_host and full_host == base_host and not any(k in full_url for k in ["generate.php", "id=", "/file/", "/d/", "/view/", "/go/", "/links/"]):
                    continue

                # If button text explicitly declares its own quality/size, prioritize it over previous header
                if QUALITY_REGEX.search(text) or SIZE_REGEX.search(text):
                    btn_mname, btn_audio, btn_codec, btn_qual, btn_size, btn_s, btn_ep = parse_movie_title_header(text)
                    eff_qual = btn_qual or quality
                    eff_codec = btn_codec if btn_codec != "HD" else codec
                    eff_size = btn_size if btn_size != "Unknown" else size_str
                    eff_audio = btn_audio if btn_audio != "Hindi & English" else audio
                else:
                    eff_qual = quality
                    eff_codec = codec
                    eff_size = size_str
                    eff_audio = audio

                unshortened_landing = None
                if "generate.php" in full_url or "id=" in full_url:
                    unwrapped = extract_url_from_query_params(full_url)
                    if unwrapped:
                        unshortened_landing = clean_cinecloud_url(unwrapped)

                seen_links.add(full_url)
                raw_items.append(
                    MediaDownloadItem(
                        title=f"{eff_codec} {eff_qual} [{eff_size}]",
                        movie_name=movie_name or default_mname,
                        quality=eff_qual,
                        codec=eff_codec,
                        size_str=eff_size,
                        audio_info=eff_audio,
                        short_link=full_url,
                        unshortened_landing_url=unshortened_landing or full_url,
                        season=season,
                        episode=episode,
                        language=lang,
                    )
                )

    # Pass 2: Fallback anchor scan for unstructured pages (only if Pass 1 yielded no items)
    if not raw_items:
        DOWNLOAD_LINK_PAT = re.compile(
            r"nexdrive\.|vcloud\.|fast-?dl\.|magiclinks\.|hubcloud\.|kmhd\.|katdrive|gdtot\.|cinecloud\.|drivehub|filebee\.|filepress\.|dgdrive\.|dropgalaxy\.|pixeldrain\.|gofile\.|streamtape\.|streamwish\.|generate\.php|drive\.|/file/|/link/|/view/|/go/|/d/",
            re.I,
        )

        all_anchors = soup.find_all("a", href=DOWNLOAD_LINK_PAT)
        for a in soup.find_all("a"):
            if a in all_anchors:
                continue
            classes = " ".join(a.get("class", [])).lower()
            text = a.get_text().strip()
            if re.search(r"dl-btn|dlbtn|download|button|btn", classes, re.I):
                all_anchors.append(a)
            elif QUALITY_REGEX.search(text) or SIZE_REGEX.search(text):
                all_anchors.append(a)

        for btn in all_anchors:
            href = btn.get("href") or ""
            if not href or href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
                continue

            full_url = urllib.parse.urljoin(base_url, href)
            if full_url in seen_links or is_ad_trap(full_url) or "vglist" in full_url.lower() or "vegamovies-apk" in full_url.lower():
                continue

            base_host = urllib.parse.urlparse(base_url).netloc.lower()
            full_host = urllib.parse.urlparse(full_url).netloc.lower()
            if base_host and full_host == base_host and not any(k in full_url for k in ["generate.php", "id=", "/file/", "/d/", "/view/", "/go/", "/links/"]):
                continue

            btn_text = btn.get_text(separator=" ").strip()
            classes = " ".join(btn.get("class", [])).lower()
            if "watch" in btn_text.lower() or "watch" in classes or "/x/" in href or "/category/" in href or "/tag/" in href:
                continue
            if any(dom in full_url.lower() for dom in ["facebook.com", "twitter.com", "t.me/", "youtube.com", "imdb.com", "how-to-download"]):
                continue

            # Prioritize button's own text if it has quality/size
            if QUALITY_REGEX.search(btn_text) or SIZE_REGEX.search(btn_text):
                _, audio, codec, quality, size_str, season, episode = parse_movie_title_header(btn_text)
            else:
                prev_h = btn.find_previous(
                    lambda tag: tag.name in ["h2", "h3", "h4", "h5", "h6", "p", "div"]
                    and tag != btn
                    and (QUALITY_REGEX.search(tag.get_text()) or SIZE_REGEX.search(tag.get_text()))
                )
                prev_text = prev_h.get_text(separator=" ").strip() if prev_h else ""
                full_ctx = f"{prev_text} {btn_text}"
                _, audio, codec, quality, size_str, season, episode = parse_movie_title_header(full_ctx)

            lang = detect_language(f"{btn_text} {default_mtitle}")
            unshortened_landing = None
            if "generate.php" in full_url or "id=" in full_url:
                unwrapped = extract_url_from_query_params(full_url)
                if unwrapped:
                    unshortened_landing = clean_cinecloud_url(unwrapped)

            seen_links.add(full_url)
            raw_items.append(
                MediaDownloadItem(
                    title=f"{codec} {quality} [{size_str}]",
                    movie_name=default_mname,
                    quality=quality,
                    codec=codec,
                    size_str=size_str,
                    audio_info=audio or "Dual Audio",
                    short_link=full_url,
                    unshortened_landing_url=unshortened_landing or full_url,
                    season=season,
                    episode=episode,
                    language=lang,
                )
            )

    # Clean and filter non-media / navigation / same-domain recommended links
    clean_media_items: List[MediaDownloadItem] = []
    for it in raw_items:
        link_low = it.short_link.lower()
        if any(bad in link_low for bad in ["/trending", "/disclaimer", "/contact", "/privacy", "/dmca", "/terms", "/about", "facebook.com", "twitter.com", "t.me/"]):
            continue
        if is_ad_trap(it.short_link) or "vglist" in link_low or "vegamovies-apk" in link_low:
            continue
        clean_media_items.append(it)

    # Drop orphan navigation / recommendation items with Unknown size if real sized buttons exist
    if any(it.size_str != "Unknown" for it in clean_media_items):
        clean_media_items = [it for it in clean_media_items if it.size_str != "Unknown"]

    # Precision Deduplication:
    # 1. Deduplicate identical download URLs
    # 2. Preserve distinct download tiers: (quality, codec, size_str, short_link)
    dedup_map: Dict[str, MediaDownloadItem] = {}
    for it in clean_media_items:
        if it.short_link not in dedup_map:
            dedup_map[it.short_link] = it

    return list(dedup_map.values())


async def extract_direct_cloud_from_d_endpoint(client: httpx.AsyncClient, d_url: str, headers: Dict[str, str], timeout: float = 3.5) -> Optional[str]:
    """Fetch /d/<id> directly to extract the Cloudflare R2 / S3 stream URL."""
    try:
        r = await client.get(d_url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            dl_btn = soup.find("a", class_=re.compile(r"download-now|btn-warning|btn-download", re.I))
            if dl_btn and dl_btn.get("href"):
                return dl_btn.get("href").replace("&amp;", "&")

            m = re.search(r'https?://[^\s"\'<>]+\.(?:r2\.cloudflarestorage\.com|amazonaws\.com)/[^\s"\'<>]+', r.text)
            if m:
                return m.group(0).replace("&amp;", "&")
    except Exception:
        pass
    return None


async def resolve_single_media_item_fast(
    item: MediaDownloadItem,
    client: httpx.AsyncClient,
    timeout: float = 4.0,
    headers: Optional[Dict[str, str]] = None,
) -> MediaDownloadItem:
    """
    Hyper-Fast Multi-Network Unshortener:
    - CineFreak / CineCloud: Base64 unwrap ➔ /d/<id> direct R2 stream
    - KatMovieHD: Auto-unlock links.kmhd.eu ➔ HubCloud ➔ Cloudflare R2 stream
    - KMmovies: MagicLinks unwrap ➔ PixelDrain direct stream / 10 Gbps servers
    - VegaMovies: NexDrive / V-Cloud unwrap ➔ Direct Cloudflare R2 stream
    """
    landing_url = item.unshortened_landing_url or item.short_link
    req_headers = headers or DEFAULT_HEADERS
    item.servers = []

    if any(k in landing_url for k in ["links.kmhd.eu", "links.kmhd.me", "kmhd."]):
        from .resolver import resolve_kmhd_page
        item.servers = await resolve_kmhd_page(client, landing_url, req_headers, timeout=timeout)
        if item.servers and item.servers[0].direct_download_url:
            item.unshortened_landing_url = item.servers[0].direct_download_url

    elif any(k in landing_url.lower() for k in ["magiclinks", "magiclinks.lol"]):
        from .resolver import resolve_magiclinks_page
        item.servers = await resolve_magiclinks_page(client, landing_url, req_headers, timeout=timeout)
        if item.servers:
            best = item.servers[0]
            item.unshortened_landing_url = best.direct_download_url or best.intermediate_url

    elif any(d in landing_url.lower() for d in ["nexdrive", "nexdrive.site", "nexdrive.pro", "nexdrive.xyz", "nexdrive.love", "nexdrive.fit"]):
        from .resolver import resolve_nexdrive_page
        item.servers = await resolve_nexdrive_page(client, landing_url, req_headers, timeout=timeout)
        if item.servers:
            best = item.servers[0]
            item.unshortened_landing_url = best.direct_download_url or best.intermediate_url

    elif any(d in landing_url.lower() for d in ["vcloud", "vcloud.fit", "vcloud.lol", "vcloud.ink"]):
        from .resolver import resolve_vcloud_page
        item.servers = await resolve_vcloud_page(client, landing_url, req_headers, timeout=timeout)
        if item.servers:
            best = item.servers[0]
            item.unshortened_landing_url = best.direct_download_url or best.intermediate_url

    elif any(d in landing_url.lower() for d in ["fastdl", "fast-dl"]):
        from .resolver.handlers.nexdrive import resolve_fastdl_page
        fast_m = await resolve_fastdl_page(client, landing_url, req_headers, timeout=timeout)
        if fast_m:
            item.servers.append(fast_m)
            item.unshortened_landing_url = fast_m.direct_download_url or fast_m.intermediate_url

    elif any(k in landing_url.lower() for k in ["hubcloud", "gamerxyt", "cinecloud", "neodrive"]):
        from .resolver.handlers.hubcloud import HubCloudHandler
        from .resolver.base import ResolutionContext
        hub = HubCloudHandler()
        ctx = ResolutionContext(timeout=timeout, extra_headers=req_headers)
        res_tuple = await hub.resolve(landing_url, client, ctx)
        if res_tuple and res_tuple[0]:
            direct_resolved = res_tuple[0]
            item.unshortened_landing_url = direct_resolved
            raw_fn = extract_filename_from_url_or_headers(direct_resolved)
            fname = sanitize_filename(raw_fn)
            item.servers.append(
                ServerMirror(
                    label="HubCloud Stream [Fast]",
                    intermediate_url=landing_url,
                    direct_download_url=direct_resolved,
                    file_name=fname,
                    server_type="Direct Stream",
                )
            )

    elif "pixeldrain" in landing_url.lower():
        m_px = re.search(r"pixeldrain\.(?:com|dev)/u/([a-zA-Z0-9_-]+)", landing_url)
        if m_px:
            px_api = f"https://pixeldrain.com/api/file/{m_px.group(1)}?download"
            item.unshortened_landing_url = px_api
            item.servers.append(
                ServerMirror(
                    label="PixelDrain [Direct 10Gbps]",
                    intermediate_url=landing_url,
                    direct_download_url=px_api,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="PixelDrain Direct",
                )
            )

    elif "streamtape.com" in landing_url.lower():
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        st_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if st_direct:
            item.unshortened_landing_url = st_direct
            item.servers.append(
                ServerMirror(
                    label="Streamtape [Direct Stream]",
                    intermediate_url=landing_url,
                    direct_download_url=st_direct,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="Streamtape Direct",
                )
            )

    elif any(w in landing_url.lower() for w in ["streamwish", "hglink.to", "swish"]):
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        sw_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if sw_direct:
            item.unshortened_landing_url = sw_direct
            item.servers.append(
                ServerMirror(
                    label="Streamwish HLS [.m3u8]",
                    intermediate_url=landing_url,
                    direct_download_url=sw_direct,
                    file_name=f"{item.movie_name}.m3u8",
                    server_type="HLS Stream",
                )
            )

    elif "gofile.io" in landing_url.lower():
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        gf_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if gf_direct:
            item.unshortened_landing_url = gf_direct
            item.servers.append(
                ServerMirror(
                    label="GoFile [Direct CDN]",
                    intermediate_url=landing_url,
                    direct_download_url=gf_direct,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="GoFile CDN",
                )
            )

    elif any(d in landing_url.lower() for d in ["doodstream.com", "dood.to", "dood.so", "dood.la", "dood.ws"]):
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        dood_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if dood_direct:
            item.unshortened_landing_url = dood_direct
            item.servers.append(
                ServerMirror(
                    label="Doodstream [Direct Video]",
                    intermediate_url=landing_url,
                    direct_download_url=dood_direct,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="Doodstream Direct",
                )
            )

    elif any(b in landing_url.lower() for b in ["bunkr.is", "bunkr.black", "bunkr.cr", "bunkr.ru", "bunkr.site"]):
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        bunkr_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if bunkr_direct:
            item.unshortened_landing_url = bunkr_direct
            item.servers.append(
                ServerMirror(
                    label="Bunkr [Direct Storage]",
                    intermediate_url=landing_url,
                    direct_download_url=bunkr_direct,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="Bunkr CDN",
                )
            )

    elif "mega.nz" in landing_url.lower():
        from .resolver.handlers.article_crawler import crawl_intermediate_server_page
        mega_direct = await crawl_intermediate_server_page(client, landing_url, req_headers, timeout=timeout)
        if mega_direct:
            item.unshortened_landing_url = mega_direct
            item.servers.append(
                ServerMirror(
                    label="Mega [Direct Cloud]",
                    intermediate_url=landing_url,
                    direct_download_url=mega_direct,
                    file_name=f"{item.movie_name}.mp4",
                    server_type="Mega CDN",
                )
            )

    else:
        if "generate.php" in landing_url or "id=" in landing_url:
            unwrapped = extract_url_from_query_params(landing_url)
            if unwrapped:
                landing_url = clean_cinecloud_url(unwrapped)
                item.unshortened_landing_url = landing_url

        file_id_match = re.search(r'/f/([a-zA-Z0-9]+)', landing_url)
        file_id = file_id_match.group(1) if file_id_match else None

        tasks = []
        if file_id and ("cinecloud" in landing_url or "neodrive" in landing_url or "hubcloud" in landing_url):
            base_domain = urllib.parse.urlparse(landing_url).netloc
            d_direct_url = f"https://{base_domain}/d/{file_id}"
            tasks.append(extract_direct_cloud_from_d_endpoint(client, d_direct_url, req_headers, timeout=timeout))

        async def fetch_landing():
            try:
                return await client.get(landing_url, headers=req_headers, timeout=timeout)
            except Exception:
                return None

        tasks.append(fetch_landing())
        results = await asyncio.gather(*tasks, return_exceptions=True)

        direct_r2_url = results[0] if len(results) > 1 and isinstance(results[0], str) else None
        landing_resp = results[-1] if len(results) >= 1 and isinstance(results[-1], httpx.Response) else None

        if direct_r2_url:
            raw_fn = extract_filename_from_url_or_headers(direct_r2_url)
            fname = sanitize_filename(raw_fn)
            item.servers.append(
                ServerMirror(
                    label="Cloud [Resumable]",
                    intermediate_url=f"https://{urllib.parse.urlparse(landing_url).netloc}/d/{file_id}" if file_id else landing_url,
                    direct_download_url=direct_r2_url,
                    file_name=fname,
                    server_type="Cloudflare R2 / S3",
                )
            )

        if landing_resp and landing_resp.status_code == 200:
            server_buttons = extract_server_options_from_html(landing_resp.text, str(landing_resp.url))
            for s_label, s_link in server_buttons:
                if is_ad_trap(s_link) or "vglist" in s_link.lower() or "vegamovies-apk" in s_link.lower():
                    continue
                if any(s_link == s.intermediate_url or s_label == s.label for s in item.servers):
                    continue
                item.servers.append(
                    ServerMirror(
                        label=s_label,
                        intermediate_url=s_link,
                        direct_download_url=None,
                        file_name="download_file",
                        server_type="Fast Server",
                    )
                )

    if not item.servers and landing_url:
        from .resolver.core import is_direct_file_url, is_direct_storage_url
        if is_direct_file_url(landing_url) or is_direct_storage_url(landing_url):
            item.servers.append(
                ServerMirror(
                    label="Direct Media Stream",
                    intermediate_url=landing_url,
                    direct_download_url=landing_url,
                    file_name=extract_filename_from_url_or_headers(landing_url),
                    server_type="Direct Stream",
                )
            )

    # Compute quality ranking scores and sort mirrors
    for m in item.servers:
        m.quality_score = calculate_quality_score(m, item.codec, item.quality)
    item.servers.sort(key=lambda s: s.quality_score, reverse=True)

    return item


async def resolve_single_media_item(
    item: MediaDownloadItem,
    client: httpx.AsyncClient,
    max_hops: int = 15,
    timeout: float = 4.0,
    headers: Optional[Dict[str, str]] = None,
) -> MediaDownloadItem:
    return await resolve_single_media_item_fast(item, client, timeout=timeout, headers=headers)


async def deep_resolve_media_items(
    items: List[MediaDownloadItem],
    max_hops: int = 15,
    timeout: float = 4.0,
    headers: Optional[Dict[str, str]] = None,
) -> List[MediaDownloadItem]:
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, limits=limits) as client:
        tasks = [resolve_single_media_item_fast(it, client, timeout=timeout, headers=headers) for it in items]
        return await asyncio.gather(*tasks)

