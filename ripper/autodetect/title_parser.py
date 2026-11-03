"""
Natural Language Title & Intent Parser.
Cleans raw search queries, extracts canonical title, release year,
quality tags, season/episode coordinates, and audio language preferences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple


# Pre-compiled noise words that people prepend or append to queries
NOISE_PATTERNS = [
    re.compile(r"\b(?:watch|stream|free\s*watch|watch\s*online)\b", re.IGNORECASE),
    re.compile(r"\b(?:download|full\s*download|direct\s*download|free\s*download)\b", re.IGNORECASE),
    re.compile(r"\b(?:full\s*movie|full\s*film|complete\s*movie|all\s*episodes)\b", re.IGNORECASE),
    re.compile(r"\b(?:hindi\s*dubbed|tamil\s*dubbed|telugu\s*dubbed|english\s*dubbed)\b", re.IGNORECASE),
    re.compile(r"\b(?:hd\s*rip|web\s*rip|bluray\s*rip|cam\s*rip|dvd\s*rip)\b", re.IGNORECASE),
    re.compile(r"\b(?:google\s*drive|hubcloud|vegamovies|katmoviehd|cinefreak|olamovies)\b", re.IGNORECASE),
    re.compile(r"\b(?:480p|720p|1080p|2160p|4k|uhd|fhd|hd)\b", re.IGNORECASE),
    re.compile(r"\b(?:mkv|mp4|avi|zip|rar|torrent|magnet)\b", re.IGNORECASE),
]

RE_YEAR = re.compile(r"\b(19\d\d|20[0-3]\d)\b")
RE_SEASON_EPISODE = re.compile(r"\b(?:s|season)[\s\._-]*(\d{1,2})(?:[\s\._-]*(?:e|ep|episode)[\s\._-]*(\d{1,3}))?\b", re.IGNORECASE)
RE_RESOLUTION = re.compile(r"\b(4k|2160p|1080p|720p|480p)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedQueryIntent:
    raw_query: str
    clean_title: str
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality_pref: Optional[str] = None
    audio_pref: Optional[str] = None
    is_tv_series: bool = False


def parse_query_intent(raw_input: str) -> ParsedQueryIntent:
    """
    Takes arbitrary casual input (e.g. 'watch oppenheimer 2023 1080p in hindi')
    and extracts clean structured title and search coordinates.
    """
    text = (raw_input or "").strip()
    if not text:
        return ParsedQueryIntent(raw_query="", clean_title="")

    # 1. Extract Year if present
    year: Optional[int] = None
    m_year = RE_YEAR.search(text)
    if m_year:
        year_cand = int(m_year.group(1))
        # Protect against titles with numbers like 1917, 2012
        if text.strip() not in ("1917", "2012", "2001"):
            year = year_cand

    # 2. Extract Season / Episode
    season: Optional[int] = None
    episode: Optional[int] = None
    is_series = False
    m_se = RE_SEASON_EPISODE.search(text)
    if m_se:
        is_series = True
        season = int(m_se.group(1))
        if m_se.group(2):
            episode = int(m_se.group(2))

    # 3. Extract Resolution
    quality_pref: Optional[str] = None
    m_res = RE_RESOLUTION.search(text)
    if m_res:
        quality_pref = m_res.group(1).lower()

    # 4. Extract Audio language
    audio_pref: Optional[str] = None
    t_lower = text.lower()
    for lang in ("hindi", "english", "tamil", "telugu", "malayalam", "kannada", "bengali", "dual", "multi"):
        if lang in t_lower:
            audio_pref = lang
            break

    # 5. Clean Title: strip noise phrases while preserving core title
    cleaned = text
    # Remove year from title string if extracted
    if year and str(year) in cleaned:
        cleaned = re.sub(rf"\b{year}\b", " ", cleaned)

    # Remove season/ep tag
    if m_se:
        cleaned = cleaned[:m_se.start()] + " " + cleaned[m_se.end():]

    # Remove noise patterns
    for pat in NOISE_PATTERNS:
        cleaned = pat.sub(" ", cleaned)

    # Remove audio language tag if extracted
    if audio_pref:
        cleaned = re.sub(rf"\b(?:in\s+)?{re.escape(audio_pref)}\b", " ", cleaned, flags=re.IGNORECASE)

    # Clean punctuation and extra whitespace
    cleaned = re.sub(r"[\[\]\(\)\{\}\_\-\:\|\+]+", " ", cleaned)
    cleaned = " ".join(cleaned.split()).strip()

    # If title was accidentally emptied (e.g. searching 'The Watch'), revert to raw
    if not cleaned:
        cleaned = text

    return ParsedQueryIntent(
        raw_query=text,
        clean_title=cleaned,
        year=year,
        season=season,
        episode=episode,
        quality_pref=quality_pref,
        audio_pref=audio_pref,
        is_tv_series=is_series,
    )
