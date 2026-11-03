"""
Universal Multi-Site Search Engine for unshorten-cli (12-Layer Beast-Mode Architecture).

Queries multiple movie/series networks in parallel with site-filtering, deduplication,
fuzzy relevance scoring, WordPress REST API & XML Sitemap cascades, and TV series grouping:
- CineFreak (cinefreak.net)
- KMmovies (kmmovies.pics)
- KatmovieHD / Katworld (new.katmoviehd.top)
- VegaMovies (vegamovies.futbol)
- OlaMovies (olamovies.mov)
- HDHub4u (hdhub4u.ms)
"""

from __future__ import annotations

import html as html_lib
import os
import re
import time
import urllib.parse
import asyncio
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import httpx
from bs4 import BeautifulSoup

from .media import (
    DEFAULT_HEADERS,
    LANGUAGE_KEYWORDS,
    LANG_DISPLAY_MAP,
    detect_language,
    extract_season_episode,
)
from .domains import get_active_domain
from .cache import GLOBAL_CACHE


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


MAX_HTML_BYTES = max(64_000, _env_int("UNSHORTEN_SEARCH_MAX_HTML_BYTES", 2_000_000))
MAX_RESULTS_PER_SITE = max(5, _env_int("UNSHORTEN_SEARCH_MAX_PER_SITE", 25))
MAX_SITEMAP_RESULTS = max(3, _env_int("UNSHORTEN_SEARCH_MAX_SITEMAP", 10))
TITLE_MAX_CHARS = max(40, _env_int("UNSHORTEN_SEARCH_TITLE_CHARS", 80))
LOCAL_FTP_BASE = _env_str("UNSHORTEN_LOCAL_FTP_BASE", "http://172.16.50.7/DHAKA-FLIX-7/")
LOCAL_MAX_DIRS = max(3, _env_int("UNSHORTEN_LOCAL_MAX_DIRS", 15))
LOCAL_MAX_FILES = max(5, _env_int("UNSHORTEN_LOCAL_MAX_FILES", 40))
SEARCH_CACHE_TTL = float(_env_int("UNSHORTEN_SEARCH_CACHE_TTL", 3600))

LOCAL_MEDIA_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v")


@dataclass
class SearchResultItem:
    site_name: str
    title: str
    url: str
    year: Optional[str] = None
    quality_tags: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    language: Optional[str] = None
    relevance_score: float = 0.0
    source_count: int = 1
    post_date: Optional[str] = None
    poster_url: Optional[str] = None
    rating: Optional[float] = None
    genre: Optional[str] = None
    tmdb_id: Optional[int] = None


@dataclass
class SearchStatus:
    site_name: str
    success: bool
    result_count: int = 0
    error_message: str = ""
    latency_ms: float = 0.0


SITE_REGISTRY: Dict[str, str] = {
    "cinefreak": "search_cinefreak_network",
    "km": "search_kmmovies_network",
    "kmmovies": "search_kmmovies_network",
    "katmovie": "search_katmoviehd_network",
    "katmoviehd": "search_katmoviehd_network",
    "katworld": "search_katmoviehd_network",
    "vega": "search_vegamovies_network",
    "vegamovies": "search_vegamovies_network",
    "ola": "search_olamovies_network",
    "olamovies": "search_olamovies_network",
    "hdhub": "search_hdhub4u_network",
    "hdhub4u": "search_hdhub4u_network",
    "bolly": "search_bollyflix_network",
    "bollyflix": "search_bollyflix_network",
    "moviesdrive": "search_moviesdrive_network",
    "moviesmod": "search_moviesmod_network",
    "uwatchfree": "search_uwatchfree_network",
    "fmoviess": "search_fmoviess_network",
    "fmovies": "search_fmoviess_network",
    "movie4k": "search_movie4k_network",
    "lookmovie": "search_lookmovie_network",
    "lookmovie2": "search_lookmovie_network",
    "mp4gana": "search_mp4gana_network",
    "bollypro": "search_bollypro_network",
    "7starhd": "search_7starhd_network",
    "starhd": "search_7starhd_network",
    "hindilinks4u": "search_hindilinks4u_network",
    "hindilinks": "search_hindilinks4u_network",
    "worldfree4u": "search_worldfree4u_network",
    "worldfree": "search_worldfree4u_network",
    "9xmovie": "search_9xmovie_network",
    "downloadhub": "search_downloadhub_network",
    "d8hub": "search_downloadhub_network",
    "movienz": "search_movienz_network",
    "filmsur": "search_filmsur_network",
    "filmshd": "search_filmshd_network",
    "local": "search_local_ftp_network",
    "moviebox": "search_moviebox_network",
    "mb": "search_moviebox_network",
    "fourkhdhub": "search_fourkhdhub_network",
    "4khdhub": "search_fourkhdhub_network",
    "torrentio": "search_torrentio_network",
}


CANONICAL_SITE_MAP: Dict[str, str] = {
    "cinefreak": "cinefreak",
    "km": "kmmovies",
    "kmmovies": "kmmovies",
    "kat": "katmoviehd",
    "katmovie": "katmoviehd",
    "katmoviehd": "katmoviehd",
    "katworld": "katmoviehd",
    "vega": "vegamovies",
    "vegamovies": "vegamovies",
    "ola": "olamovies",
    "olamovies": "olamovies",
    "hdhub": "hdhub4u",
    "hdhub4u": "hdhub4u",
    "bolly": "bollyflix",
    "bollyflix": "bollyflix",
    "drive": "moviesdrive",
    "moviesdrive": "moviesdrive",
    "moviesmod": "moviesmod",
    "mod": "moviesmod",
    "uwatch": "uwatchfree",
    "uwatchfree": "uwatchfree",
    "fmoviess": "fmoviess",
    "fmovies": "fmoviess",
    "movie4k": "movie4k",
    "lookmovie": "lookmovie",
    "lookmovie2": "lookmovie",
    "mp4gana": "mp4gana",
    "bollypro": "bollypro",
    "7starhd": "7starhd",
    "starhd": "7starhd",
    "hindilinks4u": "hindilinks4u",
    "hindilinks": "hindilinks4u",
    "worldfree4u": "worldfree4u",
    "worldfree": "worldfree4u",
    "9xmovie": "9xmovie",
    "downloadhub": "downloadhub",
    "d8hub": "downloadhub",
    "movienz": "movienz",
    "filmsur": "filmsur",
    "local": "local",
    "ftp": "local",
    "moviebox": "moviebox",
    "mb": "moviebox",
    "fourkhdhub": "fourkhdhub",
    "4khdhub": "fourkhdhub",
    "torrentio": "torrentio",
}

_DEFAULT_SITE_ORDER = [
    "moviebox", "fourkhdhub", "torrentio",
    "vegamovies", "katmoviehd", "cinefreak", "olamovies", "kmmovies", "hdhub4u",
    "fmoviess", "movie4k", "lookmovie", "bollypro", "7starhd", "hindilinks4u",
    "worldfree4u", "9xmovie", "downloadhub", "movienz", "filmsur", "filmshd",
    "mp4gana", "local",
]
_NAV_TITLES = {
    "home", "movies", "web-series", "next", "previous", "browse",
    "tv series", "how to download ?", "next ", " previous",
    "germany", "france", "united states", "india", "japan", "korea", "china",
    "romance", "action", "adventure", "drama", "thriller", "horror", "comedy",
    "sci-fi", "fantasy", "crime", "documentary", "animation", "mystery",
    "sitemap", "privacy policy", "dmca", "contact us", "disclaimer", "about us",
    "bollywood", "hollywood", "dual audio", "hindi dubbed", "south hindi",
    "k-drama", "spanish", "tamil", "telugu", "punjabi", "malayalam",
}

SearchFunc = Callable[..., Awaitable[List[SearchResultItem]]]


def resolve_site_names(site_input: Optional[str]) -> List[str]:
    """Convert user input like 'vega,kat,ola,hdhub' into canonical site keys."""
    if not site_input or site_input.lower().strip() in ("all", "*"):
        return list(_DEFAULT_SITE_ORDER)
    requested = [item.strip().lower() for item in site_input.split(",") if item.strip()]
    matched: List[str] = []
    for req in requested:
        if req in CANONICAL_SITE_MAP:
            matched.append(CANONICAL_SITE_MAP[req])
            continue
        for key, canonical in CANONICAL_SITE_MAP.items():
            if req in key or key in req:
                matched.append(canonical)
                break
    return list(dict.fromkeys(matched)) if matched else [
        "cinefreak", "kmmovies", "katmoviehd", "vegamovies", "olamovies", "hdhub4u",
        "fmoviess", "movie4k", "lookmovie", "bollyflix", "bollypro", "7starhd",
        "worldfree4u", "9xmovie", "downloadhub",
    ]


def clean_extracted_title(raw_text: str) -> str:
    """Clean extracted title string from badge junk, repeated words, and whitespace."""
    text = html_lib.unescape(raw_text or "")
    text = re.sub(
        r'^(?:Trending|HDTC|WEB-DL|BluRay|HD|HDRip|Animation|Dual Audio|English Movies|Bangla Dubbed|Hindi Dubbed|Bangla Movies|Telugu|Tamil|MCU|Bollywood|Hollywood|\s+)+',
        '',
        text,
        flags=re.I,
    )
    text = re.sub(r'^(?:Download|Watch)\s+', '', text, flags=re.I)
    text = re.sub(r'\|\s*Full Movie.*$', '', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def normalize_title_for_grouping(title: str) -> str:
    """Normalize title for grouping duplicates across sites."""
    text = (title or "").lower()
    text = re.sub(r'\(?\b(19|20)\d{2}\b\)?', '', text)
    text = re.sub(
        r'\b(2160p|4k|1080p|720p|480p|360p|uhd|hdr|bluray|web-dl|webrip|hdrip|hdcam|hevc|x265|x264|10bit)\b',
        '',
        text,
        flags=re.I,
    )
    text = re.sub(
        r'\b(hindi|english|dual|multi|tamil|telugu|malayalam|kannada|bengali|marathi|punjabi|urdu|dubbed|esub|line)\b',
        '',
        text,
        flags=re.I,
    )
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_year_from_query(query: str) -> Optional[str]:
    """Extract 4-digit release year from search query if present."""
    match = re.search(r'\b(19\d\d|20\d\d)\b', query or "")
    return match.group(1) if match else None


def filter_by_year(results: List[SearchResultItem], query_year: Optional[str]) -> List[SearchResultItem]:
    """Filter results by release year tolerance (keeps TV series or year-matched items)."""
    if not query_year:
        return results
    try:
        target = int(query_year)
    except (TypeError, ValueError):
        return results
    filtered = []
    for item in results:
        if item.season is not None:
            filtered.append(item)
        elif item.year:
            try:
                release_year = int(item.year)
                if abs(release_year - target) <= 1:
                    filtered.append(item)
            except ValueError:
                filtered.append(item)
        else:
            filtered.append(item)
    return filtered


def score_relevance(result: SearchResultItem, query: str) -> float:
    """Score a search result 0-100 based on fuzzy similarity, keywords, codec, and release year."""
    score = 0.0
    query_lower = (query or "").lower().strip()
    title_lower = (result.title or "").lower()

    fuzzy_ratio = SequenceMatcher(None, query_lower, title_lower).ratio()
    score += fuzzy_ratio * 35.0

    stop_words = {"the", "and", "for", "with", "full", "movie", "series", "download", "hindi", "dubbed", "day", "new"}
    raw_words = [word for word in query_lower.split() if len(word) >= 2 and word not in stop_words]
    query_words = set()
    for w in raw_words:
        query_words.add(w)
        if "man" in w and len(w) > 4:
            query_words.add(w.replace("man", ""))
            query_words.add("man")

    title_words = set(re.sub(r"[^\w\s]", " ", title_lower).split())
    if query_words:
        matches = sum(1 for kw in query_words if kw in title_words or any(kw in tw for tw in title_words))
        overlap = matches / len(query_words)
        score += overlap * 30.0

    year_in_query = extract_year_from_query(query)
    if year_in_query:
        if result.year == year_in_query:
            score += 15.0
        elif result.year:
            score -= 8.0

    if result.quality_tags:
        quality = result.quality_tags.upper()
        if "4K" in quality or "2160" in quality:
            score += 10.0
        elif "1080" in quality:
            score += 8.0
        elif "720" in quality:
            score += 5.0
        if "HEVC" in quality or "10BIT" in quality or "HDR" in quality:
            score += 3.0

    site_bonus = {
        "VegaMovies": 10.0,
        "KMmovies": 9.0,
        "CineFreak": 8.0,
        "KatmovieHD": 8.0,
        "OlaMovies": 8.0,
        "HDHub4u": 7.0,
        "BollyFlix": 9.0,
        "MoviesMod": 9.0,
        "UWatchFree": 8.0,
        "MoviesDrive": 8.0,
        "FMoviess": 8.0,
        "Movie4K": 8.0,
        "LookMovie": 8.0,
        "Mp4Gana": 7.0,
        "BollyPro": 9.0,
        "7StarHD": 8.0,
        "HindiLinks4u": 8.0,
        "WorldFree4u": 8.0,
        "9XMovieLive": 7.0,
        "DownloadHub": 8.0,
        "MovienZ": 7.0,
        "FilmSur": 7.0,
        "FilmsHD": 7.0,
    }
    score += site_bonus.get(result.site_name, 6.0)
    return min(100.0, max(0.0, score))


def fuzzy_filter_results(results: List[SearchResultItem], query: str, min_ratio: float = 0.20) -> List[SearchResultItem]:
    """Filter out noise results that do not match the query keywords or fuzzy threshold."""
    filtered = []
    clean_query = re.sub(r"[^\w\s]", " ", (query or "").lower()).strip()
    stop_words = {"the", "and", "for", "with", "full", "movie", "series", "download", "hindi", "dubbed", "day", "new"}
    raw_words = [word for word in clean_query.split() if len(word) >= 2 and word not in stop_words]
    
    primary_keywords = set()
    for w in raw_words:
        primary_keywords.add(w)
        if "man" in w and len(w) > 4:
            primary_keywords.add(w.replace("man", ""))
            primary_keywords.add("man")

    for item in results:
        title_lower = (item.title or "").lower()
        url_lower = (item.url or "").lower()
        ratio = SequenceMatcher(None, clean_query, re.sub(r"[^\w\s]", " ", title_lower)).ratio()
        title_words = set(re.sub(r"[^\w\s]", " ", title_lower).split())
        url_words = set(re.sub(r"[^\w\s]", " ", url_lower).split())
        all_item_words = title_words.union(url_words)
        
        keyword_match = False
        if not primary_keywords:
            keyword_match = True
        else:
            for kw in primary_keywords:
                if len(kw) >= 3 and (kw in all_item_words or any(kw in tw or tw in kw for tw in title_words)):
                    keyword_match = True
                    break
        
        if keyword_match or ratio >= 0.35:
            filtered.append(item)
    return filtered


def deduplicate_results(results: List[SearchResultItem]) -> List[SearchResultItem]:
    """Group identical movies across sites with merged quality tags and source counter."""
    if not results:
        return results

    groups: Dict[Tuple[str, Optional[int], Optional[int]], List[SearchResultItem]] = {}
    for item in results:
        norm_key = normalize_title_for_grouping(item.title)
        if not norm_key or len(norm_key) < 3:
            norm_key = (item.title or "").lower()[:30]
        group_key = (norm_key, item.season, item.episode)
        groups.setdefault(group_key, []).append(item)

    grouped_results: List[SearchResultItem] = []
    for _group_key, items in groups.items():
        best_src = max(items, key=lambda row: (row.relevance_score, row.year is not None, len(row.quality_tags or "")))
        all_tags = set()
        for item in items:
            if item.quality_tags:
                for tag in item.quality_tags.split(","):
                    cleaned = tag.strip()
                    if cleaned:
                        all_tags.add(cleaned)
        merged_tags = ", ".join(sorted(all_tags, reverse=True)) if all_tags else best_src.quality_tags
        distinct_sites = list(dict.fromkeys(row.site_name.split(" +")[0] for row in items))
        site_name = best_src.site_name
        if len(distinct_sites) > 1:
            site_name = f"{distinct_sites[0]} +{len(distinct_sites) - 1} more"
        grouped_results.append(
            replace(
                best_src,
                quality_tags=merged_tags,
                source_count=len(distinct_sites),
                site_name=site_name,
            )
        )
    return grouped_results


group_duplicate_results = deduplicate_results


def _host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url or "").netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _same_host(url: str, base: str) -> bool:
    host = _host_of(url)
    base_host = _host_of(base)
    return bool(host and base_host and host == base_host)


def _safe_json(response: Any) -> Any:
    """Parse JSON from an httpx response, or return None if the body is not JSON."""
    try:
        payload = response.json()
    except Exception:
        return None
    return payload


def _wp_title(raw: Any) -> str:
    """Normalize a WordPress title field that may be a string or {rendered: ...}."""
    if isinstance(raw, dict):
        return clean_extracted_title(str(raw.get("rendered") or raw.get("raw") or ""))
    return clean_extracted_title(str(raw or ""))


def _year_from_text(*parts: str) -> Optional[str]:
    blob = " ".join(part or "" for part in parts)
    match = re.search(r"\b(19\d\d|20\d\d)\b", blob)
    return match.group(1) if match else None


def _quality_tags_from_text(text: str, extra: Optional[str] = None, default: str = "Multi-Quality") -> str:
    blob = f"{text or ''} {extra or ''}"
    lowered = blob.lower()
    tags: List[str] = []
    if "remux" in lowered:
        tags.append("REMUX")
    if "2160" in lowered or "4k" in lowered:
        tags.append("4K UHD")
    if "1080" in blob or "1080" in lowered:
        tags.append("1080p")
    if "720" in blob:
        tags.append("720p")
    if "480" in blob:
        tags.append("480p")
    if "hevc" in lowered:
        tags.append("HEVC")
    lang = detect_language(blob)
    if lang:
        tags.append(LANG_DISPLAY_MAP.get(lang, lang.title()))
    return ", ".join(dict.fromkeys(tags)) if tags else default


def _cap_title(title: str) -> str:
    cleaned = clean_extracted_title(title)
    if len(cleaned) <= TITLE_MAX_CHARS:
        return cleaned
    return cleaned[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def _make_item(
    site_name: str,
    title: str,
    url: str,
    default_tags: str,
    extra_text: str = "",
    poster_url: Optional[str] = None,
) -> SearchResultItem:
    full = f"{title} {url} {extra_text}"
    lang = detect_language(full)
    season, episode = extract_season_episode(title)
    return SearchResultItem(
        site_name=site_name,
        title=_cap_title(title),
        url=url,
        year=_year_from_text(title, url, extra_text),
        quality_tags=_quality_tags_from_text(full, default=default_tags),
        season=season,
        episode=episode,
        language=lang,
        poster_url=poster_url,
    )


async def _read_response_text(response: Any) -> str:
    """Read at most MAX_HTML_BYTES of response text."""
    content_type = ""
    try:
        content_type = str(response.headers.get("content-type", "")).lower()
    except Exception:
        content_type = ""
    if any(prefix in content_type for prefix in ("video/", "audio/", "image/", "application/octet-stream")):
        return ""
    try:
        raw = getattr(response, "content", None)
        if isinstance(raw, (bytes, bytearray)):
            chunk = bytes(raw[:MAX_HTML_BYTES])
            return chunk.decode("utf-8", errors="replace")
    except Exception:
        pass
    try:
        text = getattr(response, "text", "") or ""
        return text[:MAX_HTML_BYTES]
    except Exception:
        return ""


async def _fetch(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[httpx.Response]:
    """GET with redirects on, used by every search tier."""
    try:
        return await client.get(
            url,
            params=params,
            headers=headers or DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


def _title_from_anchor(anchor: Any, mode: str) -> str:
    text = (anchor.get_text() or "").strip()
    if not text:
        img = anchor.find("img")
        if img and img.get("alt"):
            text = img["alt"]
    if not text and anchor.get("title"):
        text = anchor["title"]

    if mode == "cinefreak":
        title_tag = anchor.find(class_=re.compile(r"title|name", re.I))
        if title_tag:
            return clean_extracted_title(title_tag.get_text())
        cloned = BeautifulSoup(str(anchor), "html.parser").find("a")
        if cloned:
            for badge in cloned.find_all(["span", "div"], class_=re.compile(r"badge|ribbon|tag", re.I)):
                badge.decompose()
            text = cloned.get_text() or text
    elif mode == "kmmovies":
        cloned = BeautifulSoup(str(anchor), "html.parser").find("a")
        if cloned:
            for badge in cloned.find_all(["span", "div"], class_=re.compile(r"badge|rating|poster-overlay", re.I)):
                badge.decompose()
            text = cloned.get_text() or text
    return clean_extracted_title(text)


def _smart_match(query: str, title: str, href: str) -> bool:
    """Smart keyword & fuzzy filter so 'spiderman' matches 'spider-man' without matching false positives."""
    query_clean = re.sub(r"[^\w\s]", " ", (query or "").lower()).strip()
    title_clean = re.sub(r"[^\w\s]", " ", (title or "").lower()).strip()
    href_clean = href.lower().replace("-", " ").replace("_", " ").replace("/", " ")
    
    stop_words = {"the", "and", "for", "with", "full", "movie", "series", "download", "hindi", "dubbed", "day", "new"}
    raw_words = [w for w in query_clean.split() if w not in stop_words and len(w) >= 2]
    query_words = set()
    for w in raw_words:
        query_words.add(w)
        if "man" in w and len(w) > 4:
            query_words.add(w.replace("man", ""))
            query_words.add("man")
    
    title_words = set(title_clean.split())
    href_words = set(href_clean.split())
    all_words = title_words.union(href_words)

    for qw in query_words:
        if len(qw) >= 3 and (qw in all_words or any(qw in tw for tw in title_words)):
            return True
            
    if SequenceMatcher(None, query_clean, title_clean).ratio() >= 0.70:
        return True
    return False


def _should_skip_href(href: str, base_dom: str, skip_parts: Sequence[str]) -> bool:
    if not href:
        return True
    if any(part in href for part in skip_parts):
        return True
    if href.rstrip("/") == base_dom.rstrip("/"):
        return True
    return False


async def search_via_wordpress_api(
    client: httpx.AsyncClient,
    base_domain: str,
    query: str,
    site_name: str,
    timeout: float = 4.0,
) -> List[SearchResultItem]:
    """Tier 1 search: Query WordPress REST API for structured JSON with post posters."""
    results: List[SearchResultItem] = []
    endpoints = (
        (f"{base_domain}/wp-json/wp/v2/posts", {"search": query, "per_page": 20, "_fields": "link,title,date,content"}),
        (f"{base_domain}/wp-json/wp/v2/search", {"search": query, "per_page": 20, "type": "post"}),
    )
    try:
        for api_url, params in endpoints:
            response = await _fetch(client, api_url, timeout, params=params)
            if response is None or response.status_code != 200:
                continue
            data = _safe_json(response)
            if not isinstance(data, list):
                continue
            for post in data:
                if not isinstance(post, dict):
                    continue
                title = _wp_title(post.get("title", ""))
                link = post.get("url") or post.get("link") or ""
                if not title or not link:
                    continue
                if isinstance(link, dict):
                    link = str(link.get("rendered") or "")
                link = str(link).strip()
                if not link.startswith("http"):
                    link = urllib.parse.urljoin(base_domain + "/", link)

                poster_url = None
                content_raw = post.get("content", {}).get("rendered", "") if isinstance(post.get("content"), dict) else str(post.get("content") or "")
                if content_raw:
                    img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_raw)
                    valid_imgs = [img for img in img_matches if not any(k in img.lower() for k in ["bping.php", "pixel", "blank.gif", "icon", "logo", "avatar", "badge", "btn", "button"])]
                    if valid_imgs:
                        poster_url = valid_imgs[0]

                results.append(_make_item(site_name, title, link, "Multi-Quality", poster_url=poster_url))
                if len(results) >= MAX_RESULTS_PER_SITE:
                    return results
            if results:
                return results
    except asyncio.CancelledError:
        raise
    except Exception:
        return results
    return results


def _parse_sitemap_locs(body: str) -> List[str]:
    """Extract <loc> URLs cleanly with zero XML-as-HTML warnings."""
    urls: List[str] = []
    if not body:
        return urls

    # Fast direct regex extraction (100% immune to XML-as-HTML warnings)
    for match in re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", body, flags=re.I):
        u = html_lib.unescape(match).strip()
        if u and u.startswith("http") and u not in urls:
            urls.append(u)
    if urls:
        return urls

    # Fallback to BeautifulSoup with silenced XMLParsedAsHTMLWarning
    try:
        import warnings
        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    except Exception:
        pass

    parsers = ("lxml-xml", "xml", "html.parser")
    for parser in parsers:
        try:
            soup = BeautifulSoup(body, parser)
            for loc in soup.find_all("loc"):
                text = (loc.get_text() or "").strip()
                if text.startswith("http") and text not in urls:
                    urls.append(text)
            if urls:
                return urls
        except Exception:
            continue

    return urls


async def search_via_sitemap(
    client: httpx.AsyncClient,
    base_domain: str,
    query: str,
    site_name: str,
    timeout: float = 4.0,
) -> List[SearchResultItem]:
    """Tier 3 fallback: Scan WordPress XML Sitemap for matching slugs."""
    results: List[SearchResultItem] = []
    sitemap_urls = (
        f"{base_domain}/wp-sitemap-posts-post-1.xml",
        f"{base_domain}/wp-sitemap.xml",
        f"{base_domain}/sitemap.xml",
        f"{base_domain}/sitemap_index.xml",
    )
    query_words = [word.lower() for word in (query or "").split() if len(word) > 2]
    if not query_words:
        return results
    try:
        for sitemap_url in sitemap_urls:
            response = await _fetch(client, sitemap_url, timeout)
            if response is None or response.status_code != 200:
                continue
            body = await _read_response_text(response)
            for url in _parse_sitemap_locs(body):
                url_lower = url.lower()
                if not any(word in url_lower for word in query_words):
                    continue
                slug = url.rstrip("/").split("/")[-1].replace("-", " ")
                results.append(_make_item(site_name, clean_extracted_title(slug), url, "Multi-Quality"))
                if len(results) >= MAX_SITEMAP_RESULTS:
                    return results
            if results:
                return results
    except asyncio.CancelledError:
        raise
    except Exception:
        return results
    return results


async def search_with_status_tracker(
    search_func: SearchFunc,
    client: httpx.AsyncClient,
    query: str,
    site_name: str,
    timeout: float = 5.0,
) -> Tuple[List[SearchResultItem], SearchStatus]:
    """Execute search function with latency measurement and a hard timeout."""
    started = time.time()
    try:
        results = await asyncio.wait_for(search_func(client, query, timeout=timeout), timeout=timeout + 1.5)
        latency = (time.time() - started) * 1000.0
        return results, SearchStatus(
            site_name=site_name,
            success=True,
            result_count=len(results),
            latency_ms=latency,
        )
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        latency = (time.time() - started) * 1000.0
        return [], SearchStatus(
            site_name=site_name,
            success=False,
            error_message=f"{site_name} took too long to answer. Try again, or raise the timeout.",
            latency_ms=latency,
        )
    except Exception as exc:
        latency = (time.time() - started) * 1000.0
        return [], SearchStatus(
            site_name=site_name,
            success=False,
            error_message=f"{site_name} failed: {exc}. Check the site domain or try another mirror.",
            latency_ms=latency,
        )


async def _html_search(
    client: httpx.AsyncClient,
    query: str,
    base_dom: str,
    site_name: str,
    timeout: float,
    skip_parts: Sequence[str],
    default_tags: str,
    title_mode: str = "simple",
    extra_nav: Optional[Set[str]] = None,
    require_same_host: bool = True,
) -> List[SearchResultItem]:
    """Shared HTML search-page scraper used by every network."""
    results: List[SearchResultItem] = []
    search_url = f"{base_dom}/?s={urllib.parse.quote_plus(query)}"
    response = await _fetch(client, search_url, timeout)
    if response is None or response.status_code != 200:
        return results
    body = await _read_response_text(response)
    if not body:
        return results

    soup = BeautifulSoup(body, "html.parser")
    seen_urls: Set[str] = set()
    blocked = set(_NAV_TITLES)
    if extra_nav:
        blocked.update(extra_nav)

    for anchor in soup.find_all("a"):
        raw_href = (anchor.get("href") or "").strip()
        href = urllib.parse.urljoin(base_dom + "/", raw_href)
        if href in seen_urls:
            continue
        if _should_skip_href(href, base_dom, skip_parts):
            continue
        if require_same_host and not _same_host(href, base_dom):
            continue
        if not href.startswith("http"):
            continue

        title = _title_from_anchor(anchor, title_mode)
        if not title or len(title) < 3 or title.lower() in blocked:
            continue
        if not _smart_match(query, title, href):
            continue

        # Extract poster image from anchor or parent card
        poster_url = None
        img = anchor.find("img")
        if not img:
            parent = anchor.find_parent(["article", "div", "li"])
            if parent:
                img = parent.find("img")
        if img:
            src = img.get("data-src") or img.get("data-lazy-src") or img.get("src") or (img.get("srcset", "").split()[0] if img.get("srcset") else None)
            if src and not any(k in src.lower() for k in [".svg", "emoji", "reaction", "bping.php", "pixel", "blank.gif", "icon", "logo", "avatar", "badge", "btn", "button"]):
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = urllib.parse.urljoin(base_dom + "/", src)
                poster_url = src

        seen_urls.add(href)
        results.append(_make_item(site_name, title, href, default_tags, poster_url=poster_url))
        if len(results) >= MAX_RESULTS_PER_SITE:
            break
    return results


async def search_cinefreak_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search cinefreak.net with dual cascade (WP API + HTML Scraping + Sitemap)."""
    base_dom = await get_active_domain("cinefreak", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "CineFreak", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "CineFreak",
        timeout,
        skip_parts=("/category/", "?s=", "/page/"),
        default_tags="1080p, 720p, 480p",
        title_mode="cinefreak",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    if not combined:
        return await search_via_sitemap(client, base_dom, query, "CineFreak", timeout=min(timeout, 3.0))
    return combined


async def search_kmmovies_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search kmmovies.pics with dual cascade (WP API + HTML Scraping + Sitemap)."""
    base_dom = await get_active_domain("kmmovies", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "KMmovies", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "KMmovies",
        timeout,
        skip_parts=("/category/", "/genre/", "/page/"),
        default_tags="4K / 1080p / 720p",
        title_mode="kmmovies",
        extra_nav={"tv series", "browse"},
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    if not combined:
        return await search_via_sitemap(client, base_dom, query, "KMmovies", timeout=min(timeout, 3.0))
    return combined


async def search_katmoviehd_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search KatmovieHD / Katworld with dual cascade."""
    base_dom = await get_active_domain("katmoviehd", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "KatmovieHD", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "KatmovieHD",
        timeout,
        skip_parts=("/category/", "/page/", "/tag/"),
        default_tags="1080p / 720p / 480p",
        extra_nav={"how to download ?"},
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_vegamovies_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search VegaMovies Typesense API with automatic fallback to direct search."""
    results: List[SearchResultItem] = []
    active_domain = await get_active_domain("vegamovies", client)
    if not active_domain:
        return results

    try:
        api_url = f"{active_domain}/ts-search.php?q={urllib.parse.quote_plus(query)}&page=1"
        referer = f"{active_domain}/search.html?q={urllib.parse.quote_plus(query)}"
        response = await _fetch(
            client,
            api_url,
            timeout,
            headers={**DEFAULT_HEADERS, "Referer": referer},
        )
        if response is not None and response.status_code == 200:
            data = _safe_json(response)
            hits = data.get("hits") if isinstance(data, dict) else None
            if isinstance(hits, list):
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    doc = hit.get("document") or {}
                    if not isinstance(doc, dict):
                        continue
                    raw_title = doc.get("post_title", "")
                    permalink = doc.get("permalink", "")
                    if not raw_title or not permalink:
                        continue
                    full_url = urllib.parse.urljoin(active_domain + "/", str(permalink))
                    post_thumb = doc.get("post_thumbnail")
                    results.append(_make_item("VegaMovies", str(raw_title), full_url, "4K / 1080p / 720p", poster_url=post_thumb))
                    if len(results) >= MAX_RESULTS_PER_SITE:
                        break
                if results:
                    return results
    except asyncio.CancelledError:
        raise
    except Exception:
        pass

    return await _html_search(
        client,
        query,
        active_domain,
        "VegaMovies",
        timeout,
        skip_parts=("/category/", "/page/", "?s="),
        default_tags="4K / 1080p",
    )


async def search_olamovies_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search OlaMovies network for high-bitrate REMUX & 4K streams."""
    base_dom = await get_active_domain("olamovies", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "OlaMovies", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "OlaMovies",
        timeout,
        skip_parts=("/category/", "/tag/", "/page/", "?s="),
        default_tags="1080p / 720p / REMUX",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_hdhub4u_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search HDHub4u network with multi-tier cascade."""
    base_dom = await get_active_domain("hdhub4u", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "HDHub4u", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "HDHub4u",
        timeout,
        skip_parts=("/category/", "/tag/", "/page/"),
        default_tags="Multi-Quality",
        require_same_host=True,
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_bollyflix_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search BollyFlix network for Bollywood & Hollywood Dual Audio."""
    base_dom = await get_active_domain("bollyflix", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "BollyFlix", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "BollyFlix",
        timeout,
        skip_parts=("/category/", "/page/", "/tag/", "?s="),
        default_tags="4K / 1080p / 720p Dual Audio",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_topmovies_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search TopMovies network."""
    base_dom = await get_active_domain("topmovies", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "TopMovies", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "TopMovies",
        timeout,
        skip_parts=("/category/", "/page/", "/genre/"),
        default_tags="1080p / 720p / 480p",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_moviesmod_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search MoviesMod network."""
    base_dom = await get_active_domain("moviesmod", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "MoviesMod", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "MoviesMod",
        timeout,
        skip_parts=("/category/", "/page/", "/tag/"),
        default_tags="4K / 1080p / 720p",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_uwatchfree_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search UWatchFree network."""
    base_dom = await get_active_domain("uwatchfree", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "UWatchFree", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "UWatchFree",
        timeout,
        skip_parts=("/category/", "/page/", "/genre/"),
        default_tags="1080p / 720p / HD",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_moviesdrive_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search MoviesDrive network."""
    base_dom = await get_active_domain("moviesdrive", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "MoviesDrive", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client,
        query,
        base_dom,
        "MoviesDrive",
        timeout,
        skip_parts=("/category/", "/page/", "/genre/"),
        default_tags="1080p / 720p / HEVC",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    return combined


async def search_local_ftp_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Targeted local movie server crawler. Searches directories and files matching query keywords."""
    results: List[SearchResultItem] = []
    base_url = LOCAL_FTP_BASE if LOCAL_FTP_BASE.endswith("/") else LOCAL_FTP_BASE + "/"
    words = [word.lower() for word in (query or "").split() if len(word) > 2]
    if not words:
        words = [(query or "").lower()] if query else []
    if not words:
        return results

    queue = [base_url]
    visited: Set[str] = set()
    checked_dirs = 0
    base_host = _host_of(base_url)

    async def _online() -> bool:
        try:
            probe = await client.head(base_url, timeout=1.5, follow_redirects=True)
            if probe.status_code == 405:
                return True
            return probe.status_code < 500
        except asyncio.CancelledError:
            raise
        except Exception:
            try:
                probe = await client.get(base_url, timeout=1.5, follow_redirects=True)
                return probe.status_code < 500
            except asyncio.CancelledError:
                raise
            except Exception:
                return False

    if not await _online():
        return results

    try:
        while queue and checked_dirs < LOCAL_MAX_DIRS and len(results) < LOCAL_MAX_FILES:
            current_url = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)
            checked_dirs += 1

            response = await _fetch(client, current_url, timeout)
            if response is None or response.status_code != 200:
                continue
            body = await _read_response_text(response)
            soup = BeautifulSoup(body, "html.parser")
            for anchor in soup.find_all("a"):
                href = (anchor.get("href") or "").strip()
                if not href or href.startswith("?") or href.startswith("#") or href in ("../", "./"):
                    continue
                full_url = urllib.parse.urljoin(current_url, href)
                if _host_of(full_url) != base_host:
                    continue
                text = html_lib.unescape((anchor.get_text() or "").strip())
                is_dir = href.endswith("/") or ("." not in href.rstrip("/").split("/")[-1])
                title_lower = f"{text} {href}".lower()
                matches = any(word in title_lower for word in words)
                if is_dir:
                    if matches or any(
                        token in title_lower
                        for token in ("movie", "show", "series", "season", "video", "download", "hunts", "media")
                    ):
                        queue.append(full_url)
                    continue
                path_lower = href.lower()
                if matches and any(path_lower.endswith(ext) for ext in LOCAL_MEDIA_EXTENSIONS):
                    results.append(
                        SearchResultItem(
                            site_name="Local Server",
                            title=_cap_title(text or path_lower.split("/")[-1]),
                            url=full_url,
                            year=_year_from_text(text),
                            quality_tags="Local Direct Stream",
                        )
                    )
                    if len(results) >= LOCAL_MAX_FILES:
                        break
    except asyncio.CancelledError:
        raise
    except Exception:
        return results
    return results


def _dyn_search_factory(discovered_site: Any) -> SearchFunc:
    """Build a search callable for a SiteHunter-discovered domain."""

    async def _dyn_search(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
        from .hunter.auto_scraper import auto_search_site

        fingerprint = {
            "search_type": "wordpress_query" if getattr(discovered_site, "is_wordpress", False) else "generic",
            "search_endpoint": getattr(discovered_site, "search_endpoint", None),
        }
        raw_items = await auto_search_site(client, discovered_site.url, query, fingerprint)
        items: List[SearchResultItem] = []
        for row in raw_items or []:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "")
            url = str(row.get("url") or "")
            if not title or not url:
                continue
            items.append(
                SearchResultItem(
                    site_name=str(getattr(discovered_site, "domain", "Mirror")).capitalize(),
                    title=_cap_title(title),
                    url=url,
                    year=_year_from_text(title),
                    quality_tags="HD",
                )
            )
            if len(items) >= MAX_RESULTS_PER_SITE:
                break
        return items

    return _dyn_search


async def _generic_wp_search(
    client: httpx.AsyncClient,
    query: str,
    site_key: str,
    site_name: str,
    default_tags: str,
    timeout: float = 5.0,
) -> List[SearchResultItem]:
    """Generic search for any WordPress movie site: WP API -> HTML -> Sitemap."""
    base_dom = await get_active_domain(site_key, client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, site_name, timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client, query, base_dom, site_name, timeout,
        skip_parts=("/category/", "/genre/", "/country/", "/tag/", "/cast/", "/actor/", "/director/", "/page/", "?s="),
        default_tags=default_tags,
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    if not combined:
        return await search_via_sitemap(client, base_dom, query, site_name, timeout=min(timeout, 3.0))
    return combined


async def search_fmoviess_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search fmoviess.org — Hollywood/International streaming."""
    return await _generic_wp_search(client, query, "fmoviess", "FMoviess", "HD / 1080p / 720p", timeout)


async def search_movie4k_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search movie4kto.xyz — Hollywood 4K / HD movies."""
    return await _generic_wp_search(client, query, "movie4k", "Movie4K", "4K / 1080p / 720p", timeout)


async def search_lookmovie_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search lookmovie2.city — Hollywood movies and TV."""
    return await _generic_wp_search(client, query, "lookmovie", "LookMovie", "HD / 1080p", timeout)


async def search_mp4gana_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search mp4gana.com — Tamil / South Indian movies."""
    return await _generic_wp_search(client, query, "mp4gana", "Mp4Gana", "HD / 720p Tamil", timeout)


async def search_bollypro_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search bollypro.com — Bollywood Hindi movies."""
    return await _generic_wp_search(client, query, "bollypro", "BollyPro", "1080p / 720p Hindi", timeout)


async def search_7starhd_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search 7starhd.latino — Hindi Dubbed / Bollywood."""
    return await _generic_wp_search(client, query, "7starhd", "7StarHD", "1080p / 720p Dual Audio", timeout)


async def search_hindilinks4u_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search hindilinks4u.estate — Hindi movie links."""
    return await _generic_wp_search(client, query, "hindilinks4u", "HindiLinks4u", "HD Hindi", timeout)


async def search_worldfree4u_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search worldfree4u.gd — Multi-language multi-quality."""
    return await _generic_wp_search(client, query, "worldfree4u", "WorldFree4u", "4K / 1080p / 720p Multi", timeout)


async def search_9xmovie_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search 9xmovielive.com — Hindi / Bollywood movies."""
    return await _generic_wp_search(client, query, "9xmovie", "9XMovieLive", "1080p / 720p Hindi", timeout)


async def search_downloadhub_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search downloadhub.ac — Multi-quality download hub."""
    base_dom = await get_active_domain("downloadhub", client)
    if not base_dom:
        # Try d8hub mirror
        base_dom = await get_active_domain("d8hub", client)
    if not base_dom:
        return []
    combined: List[SearchResultItem] = []
    seen: Set[str] = set()
    wp_res = await search_via_wordpress_api(client, base_dom, query, "DownloadHub", timeout=min(timeout, 3.0))
    for item in wp_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    html_res = await _html_search(
        client, query, base_dom, "DownloadHub", timeout,
        skip_parts=("/category/", "/page/", "?s="),
        default_tags="4K / 1080p / 720p / 480p",
    )
    for item in html_res:
        if item.url not in seen:
            seen.add(item.url)
            combined.append(item)
    if not combined:
        return await search_via_sitemap(client, base_dom, query, "DownloadHub", timeout=min(timeout, 3.0))
    return combined


async def search_movienz_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search movienz.com — International movies."""
    return await _generic_wp_search(client, query, "movienz", "MovienZ", "HD / 1080p", timeout)


async def search_filmsur_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search filmsur.com — Hollywood movies."""
    return await _generic_wp_search(client, query, "filmsur", "FilmSur", "HD / 1080p", timeout)


async def search_filmshd_network(client: httpx.AsyncClient, query: str, timeout: float = 5.0) -> List[SearchResultItem]:
    """Search filmshd.org — Hollywood and Bollywood movies."""
    return await _generic_wp_search(client, query, "filmshd", "FilmsHD", "HD / 1080p", timeout)


async def search_moviebox_network(client: httpx.AsyncClient, query: str, timeout: float = 6.0) -> List[SearchResultItem]:
    """Search MovieBox Mobile BFF with HMAC-MD5 signing and multi-host failover."""
    from .portals.moviebox import MovieBoxPortal
    portal = MovieBoxPortal(timeout=timeout)
    results = await portal.search(query, limit=MAX_RESULTS_PER_SITE)
    items: List[SearchResultItem] = []
    for r in results:
        items.append(
            _make_item(
                site_name="MovieBox",
                title=r.title,
                url=r.url,
                default_tags=r.quality or "1080p, HD",
                poster_url=r.poster_url,
            )
        )
    return items


async def search_fourkhdhub_network(client: httpx.AsyncClient, query: str, timeout: float = 6.0) -> List[SearchResultItem]:
    """Search 4KHDHub & HubCloud network."""
    return await _generic_wp_search(client, query, "4khdhub", "4KHDHub", "4K / 1080p", timeout)


async def search_torrentio_network(client: httpx.AsyncClient, query: str, timeout: float = 6.0) -> List[SearchResultItem]:
    """Search Torrentio Stremio Addon & Real-Debrid cached streams."""
    from .debrid import TorrentioClient
    t_client = TorrentioClient(timeout=timeout)
    clean_q = query.strip()
    imdb_id = clean_q if clean_q.startswith("tt") else None
    if not imdb_id:
        try:
            for ctype in ("movie", "series"):
                cm_url = f"https://v3-cinemeta.strem.io/catalog/{ctype}/top/search={urllib.parse.quote(clean_q)}.json"
                resp = await client.get(cm_url, timeout=timeout)
                if resp.status_code == 200:
                    metas = resp.json().get("metas", [])
                    if metas and (metas[0].get("id") or metas[0].get("imdb_id")):
                        imdb_id = metas[0].get("id") or metas[0].get("imdb_id")
                        break
        except Exception:
            pass
    if not imdb_id:
        return []
    releases = await t_client.resolve(imdb_id)
    items: List[SearchResultItem] = []
    for rel in releases:
        items.append(
            _make_item(
                site_name="Torrentio" + (" (RD+)" if rel.is_cached else ""),
                title=rel.title,
                url=rel.stream_url or f"magnet:?xt=urn:btih:{rel.info_hash}",
                default_tags=rel.quality,
            )
        )
    return items


async def execute_multi_site_search(
    query: str,
    timeout: float = 5.0,
    target_sites: Optional[List[str]] = None,
    query_year: Optional[str] = None,
    use_cache: bool = True,
) -> Tuple[List[SearchResultItem], List[SearchStatus]]:
    """
    Execute concurrent multi-site search with timeout isolation, fuzzy filtering,
    release year matching, deduplication, and relevance scoring.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return [], [
            SearchStatus(
                site_name="Search",
                success=False,
                error_message="No search text was provided. Type a movie or series name and try again.",
            )
        ]

    cache_key = f"{clean_query.lower()}_{query_year or ''}_{','.join(sorted(target_sites)) if target_sites else 'all'}"
    if use_cache:
        try:
            cached = await GLOBAL_CACHE.get("search", cache_key)
            if cached:
                return cached, [
                    SearchStatus(
                        site_name="Cache (In-Memory)",
                        success=True,
                        result_count=len(cached),
                        latency_ms=0.0,
                    )
                ]
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    limits = httpx.Limits(max_connections=60, max_keepalive_connections=30)
    async with httpx.AsyncClient(
        timeout=timeout,
        verify=False,
        follow_redirects=True,
        limits=limits,
        headers=DEFAULT_HEADERS,
    ) as client:
        tasks = []
        active_sites = resolve_site_names(",".join(target_sites) if target_sites else "all")

        if any(site in active_sites for site in ("moviebox", "mb")):
            tasks.append(search_with_status_tracker(search_moviebox_network, client, clean_query, "MovieBox", timeout=timeout))
        if any(site in active_sites for site in ("fourkhdhub", "4khdhub")):
            tasks.append(search_with_status_tracker(search_fourkhdhub_network, client, clean_query, "4KHDHub", timeout=timeout))
        if "torrentio" in active_sites:
            tasks.append(search_with_status_tracker(search_torrentio_network, client, clean_query, "Torrentio", timeout=timeout))

        if "cinefreak" in active_sites:
            tasks.append(search_with_status_tracker(search_cinefreak_network, client, clean_query, "CineFreak", timeout=timeout))
        if any(site in active_sites for site in ("km", "kmmovies")):
            tasks.append(search_with_status_tracker(search_kmmovies_network, client, clean_query, "KMmovies", timeout=timeout))
        if any(site in active_sites for site in ("katmovie", "katmoviehd", "katworld")):
            tasks.append(search_with_status_tracker(search_katmoviehd_network, client, clean_query, "KatmovieHD", timeout=timeout))
        if any(site in active_sites for site in ("vega", "vegamovies")):
            tasks.append(search_with_status_tracker(search_vegamovies_network, client, clean_query, "VegaMovies", timeout=timeout))
        if any(site in active_sites for site in ("ola", "olamovies")):
            tasks.append(search_with_status_tracker(search_olamovies_network, client, clean_query, "OlaMovies", timeout=timeout))
        if any(site in active_sites for site in ("hdhub", "hdhub4u")):
            tasks.append(search_with_status_tracker(search_hdhub4u_network, client, clean_query, "HDHub4u", timeout=timeout))
        if any(site in active_sites for site in ("bolly", "bollyflix")):
            tasks.append(search_with_status_tracker(search_bollyflix_network, client, clean_query, "BollyFlix", timeout=timeout))
        if any(site in active_sites for site in ("mod", "moviesmod")):
            tasks.append(search_with_status_tracker(search_moviesmod_network, client, clean_query, "MoviesMod", timeout=timeout))
        if any(site in active_sites for site in ("uwatch", "uwatchfree")):
            tasks.append(search_with_status_tracker(search_uwatchfree_network, client, clean_query, "UWatchFree", timeout=timeout))
        if any(site in active_sites for site in ("drive", "moviesdrive")):
            tasks.append(search_with_status_tracker(search_moviesdrive_network, client, clean_query, "MoviesDrive", timeout=timeout))
        if any(site in active_sites for site in ("fmoviess", "fmovies")):
            tasks.append(search_with_status_tracker(search_fmoviess_network, client, clean_query, "FMoviess", timeout=timeout))
        if "movie4k" in active_sites:
            tasks.append(search_with_status_tracker(search_movie4k_network, client, clean_query, "Movie4K", timeout=timeout))
        if any(site in active_sites for site in ("lookmovie", "lookmovie2")):
            tasks.append(search_with_status_tracker(search_lookmovie_network, client, clean_query, "LookMovie", timeout=timeout))
        if "mp4gana" in active_sites:
            tasks.append(search_with_status_tracker(search_mp4gana_network, client, clean_query, "Mp4Gana", timeout=timeout))
        if "bollypro" in active_sites:
            tasks.append(search_with_status_tracker(search_bollypro_network, client, clean_query, "BollyPro", timeout=timeout))
        if any(site in active_sites for site in ("7starhd", "starhd")):
            tasks.append(search_with_status_tracker(search_7starhd_network, client, clean_query, "7StarHD", timeout=timeout))
        if any(site in active_sites for site in ("hindilinks4u", "hindilinks")):
            tasks.append(search_with_status_tracker(search_hindilinks4u_network, client, clean_query, "HindiLinks4u", timeout=timeout))
        if any(site in active_sites for site in ("worldfree4u", "worldfree")):
            tasks.append(search_with_status_tracker(search_worldfree4u_network, client, clean_query, "WorldFree4u", timeout=timeout))
        if "9xmovie" in active_sites:
            tasks.append(search_with_status_tracker(search_9xmovie_network, client, clean_query, "9XMovieLive", timeout=timeout))
        if any(site in active_sites for site in ("downloadhub", "d8hub")):
            tasks.append(search_with_status_tracker(search_downloadhub_network, client, clean_query, "DownloadHub", timeout=timeout))
        if "movienz" in active_sites:
            tasks.append(search_with_status_tracker(search_movienz_network, client, clean_query, "MovienZ", timeout=timeout))
        if "filmsur" in active_sites:
            tasks.append(search_with_status_tracker(search_filmsur_network, client, clean_query, "FilmSur", timeout=timeout))
        if "filmshd" in active_sites:
            tasks.append(search_with_status_tracker(search_filmshd_network, client, clean_query, "FilmsHD", timeout=timeout))
        if "local" in active_sites:
            tasks.append(search_with_status_tracker(search_local_ftp_network, client, clean_query, "Local Server", timeout=timeout))

        if not target_sites:
            try:
                from .hunter.site_db import SiteHunter

                hunter = SiteHunter()
                extra_sites = [
                    site
                    for site in getattr(hunter, "db", {}).values()
                    if getattr(site, "is_alive", False)
                    and getattr(site, "domain", "")
                    not in {
                        "cinefreak.net",
                        "kmmovies.pics",
                        "new.katmoviehd.top",
                        "vegamovies.ph",
                        "olamovies.art",
                        "hdhub4u.bi",
                    }
                ]
                for discovered in extra_sites[:6]:
                    label = str(getattr(discovered, "domain", "Mirror")).capitalize()
                    tasks.append(
                        search_with_status_tracker(
                            _dyn_search_factory(discovered),
                            client,
                            clean_query,
                            label,
                            timeout=timeout,
                        )
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

        result_sets = await asyncio.gather(*tasks, return_exceptions=True)

        combined: List[SearchResultItem] = []
        statuses: List[SearchStatus] = []
        for row in result_sets:
            if isinstance(row, asyncio.CancelledError):
                raise row
            if isinstance(row, Exception):
                statuses.append(
                    SearchStatus(
                        site_name="Search",
                        success=False,
                        error_message=f"A search worker crashed: {row}",
                    )
                )
                continue
            if isinstance(row, tuple) and len(row) == 2:
                items, status = row
                if isinstance(items, list):
                    combined.extend(items)
                if isinstance(status, SearchStatus):
                    statuses.append(status)

        filtered = fuzzy_filter_results(combined, clean_query, min_ratio=0.25)
        effective_year = query_year or extract_year_from_query(clean_query)
        if effective_year:
            filtered = filter_by_year(filtered, effective_year)
        for item in filtered:
            item.relevance_score = score_relevance(item, clean_query)
        final_results = deduplicate_results(filtered)
        final_results.sort(key=lambda item: item.relevance_score, reverse=True)
        if any(item.relevance_score >= 40.0 for item in final_results):
            final_results = [item for item in final_results if item.relevance_score >= 15.0]

        if use_cache and final_results:
            try:
                await GLOBAL_CACHE.set("search", cache_key, final_results, ttl=SEARCH_CACHE_TTL)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

        return final_results, statuses
