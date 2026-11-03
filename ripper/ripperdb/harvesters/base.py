"""
ripper.ripperdb.harvesters.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Abstract Base Class and common utilities for archetype-driven media harvesters.
Provides connection pooling with Chrome 124 TLS impersonation via curl_cffi,
circuit breaking, quality scoring heuristics, and clean data normalization.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ripper.ripperdb.cache import (
    CachedStream,
    ReleaseItem,
    estimate_stream_ttl,
    generate_item_id,
    generate_stream_id,
    normalize_title,
)

logger = logging.getLogger("ripper.ripperdb.harvesters.base")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "it", "this", "that", "hd", "full"
}


def extract_title_and_year(query_or_title: str) -> Tuple[str, Optional[int]]:
    """Extracts clean title string and 4-digit release year if present."""
    match = re.search(r"\b(19\d\d|20\d\d)\b", query_or_title)
    year = int(match.group(1)) if match else None
    clean = re.sub(r"\[.*?\]", " ", query_or_title)
    clean = re.sub(r"\b(19\d\d|20\d\d)\b", " ", clean)
    clean = re.sub(r"[\(\)\[\]\{\}]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean, year


def is_title_relevant(
    candidate_title: str,
    query: str,
    min_ratio: float = 0.50,
    query_year: Optional[int] = None,
) -> bool:
    """
    Precision multi-factor relevance gate.
    Prevents sidebar recommendation cards, recent uploads, and popular movie grids
    from leaking into search results when a site returns 0 true matches.
    """
    if not candidate_title or not query:
        return False

    import difflib
    q_clean, q_yr = extract_title_and_year(query)
    target_year = query_year or q_yr

    c_clean, c_yr = extract_title_and_year(candidate_title)

    # Year gating: If both search query and candidate title have explicit years,
    # reject if mismatched by more than 1 year
    if target_year and c_yr and abs(target_year - c_yr) > 1:
        return False

    q_norm = normalize_title(q_clean)
    c_norm = normalize_title(c_clean)

    if not q_norm or not c_norm:
        return False

    # Exact substring match
    if q_norm in c_norm or c_norm in q_norm:
        return True

    # Token overlap check
    q_tokens = [w for w in q_norm.split() if w not in STOP_WORDS and len(w) >= 2]
    c_tokens = [w for w in c_norm.split() if w not in STOP_WORDS and len(w) >= 2]

    if not q_tokens:
        q_tokens = q_norm.split()
    if not c_tokens:
        c_tokens = c_norm.split()

    matched_tokens = 0
    for qt in q_tokens:
        if any(qt == ct or (len(qt) >= 4 and qt in ct) or (len(ct) >= 4 and ct in qt) for ct in c_tokens):
            matched_tokens += 1

    # If ZERO significant words match, it's 100% irrelevant
    if matched_tokens == 0:
        return False

    # Calculate token match ratio
    token_ratio = matched_tokens / max(1, len(q_tokens))
    if token_ratio >= 0.50:
        return True

    # Sequence similarity
    seq_ratio = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
    if seq_ratio >= min_ratio:
        return True

    return False


def calculate_quality_score(
    resolution: Optional[str] = None,
    codec: Optional[str] = None,
    seeders: Optional[int] = None,
    is_direct_cdn: bool = False,
    audio_channels: Optional[str] = None,
    hdr_type: Optional[str] = None,
    size_gb: Optional[float] = None,
) -> float:
    """Computes a precision quality score (0.0 - 100.0) based on resolution, codec, audio, and health."""
    score = 50.0

    # Resolution weight
    res_lower = (resolution or "").lower()
    if "2160" in res_lower or "4k" in res_lower:
        score += 35.0
    elif "1080" in res_lower or "fhd" in res_lower:
        score += 25.0
    elif "720" in res_lower or "hd" in res_lower:
        score += 10.0
    elif "480" in res_lower or "sd" in res_lower:
        score -= 10.0

    # Codec efficiency weight
    codec_lower = (codec or "").lower()
    if "av1" in codec_lower:
        score += 10.0
    elif "hevc" in codec_lower or "x265" in codec_lower or "h265" in codec_lower:
        score += 8.0
    elif "x264" in codec_lower or "h264" in codec_lower:
        score += 3.0

    # HDR / Color grading bonus
    hdr_lower = (hdr_type or "").lower()
    if "dv" in hdr_lower or "dolby vision" in hdr_lower:
        score += 8.0
    elif "hdr10+" in hdr_lower or "hdr10plus" in hdr_lower:
        score += 6.0
    elif "hdr" in hdr_lower:
        score += 4.0

    # Audio channel depth
    audio_lower = (audio_channels or "").lower()
    if "atmos" in audio_lower or "truehd" in audio_lower:
        score += 8.0
    elif "7.1" in audio_lower:
        score += 6.0
    elif "5.1" in audio_lower:
        score += 4.0

    # Direct high-speed CDN bonus
    if is_direct_cdn:
        score += 5.0

    # Bitrate / Size indicator
    if size_gb is not None:
        if size_gb >= 15.0:  # 4K Remux quality
            score += 10.0
        elif size_gb >= 4.0:   # High-bitrate 1080p
            score += 5.0
        elif size_gb < 0.6 and ("1080" in res_lower or "2160" in res_lower):  # Severely starved
            score -= 15.0

    # Peer health weight for torrents
    if seeders is not None:
        if seeders > 100:
            score += 10.0
        elif seeders > 20:
            score += 5.0
        elif seeders < 3:
            score -= 15.0

    return max(0.0, min(100.0, score))


@dataclass
class HarvesterHealth:
    consecutive_failures: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    last_latency_ms: float = 0.0
    is_open: bool = False  # Circuit breaker state
    last_error: Optional[str] = None


class BaseHarvester(ABC):
    """
    Abstract Base Class for all archetype harvesters.
    Subclasses implement extraction logic tailored to their site architecture.
    """

    def __init__(self, timeout: float = 12.0, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self.health = HarvesterHealth()

    @property
    @abstractmethod
    def archetype(self) -> str:
        """Returns the archetype identifier (e.g. 'pstream', 'dooplay', 'embed', 'torrent', 'ddl')."""
        pass

    @abstractmethod
    async def search(
        self,
        provider_id: str,
        base_url: str,
        query: str,
        year: Optional[int] = None,
    ) -> List[ReleaseItem]:
        """
        Executes search against target provider and returns structured release items.
        """
        pass

    @abstractmethod
    async def extract_stream(
        self,
        item: ReleaseItem,
        provider_url: str,
    ) -> Optional[CachedStream]:
        """
        Resolves a release item into a direct playable stream link or download manifest.
        """
        pass

    async def fetch_text(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[int, str]:
        """
        Performs resilient HTTP GET using Chrome 124 TLS impersonation or httpx.
        Returns (status_code, response_text).
        """
        t = timeout or self.timeout
        req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        if headers:
            req_headers.update(headers)

        # 1. Attempt BypassLadder (L0 curl_cffi -> L1 cookies -> L2 companion, never spawn headless during search)
        try:
            from ripper.bypass.ladder import GLOBAL_BYPASS
            status, text, _ = await GLOBAL_BYPASS.fetch(url, headers=req_headers, allow_headless=False)
            if status == 200 or (status < 400 and text):
                return status, text
        except Exception as e:
            logger.debug("GLOBAL_BYPASS attempt failed for %s: %s", url, e)

        loop = asyncio.get_running_loop()

        # 2. Synchronous curl_cffi in executor with Chrome 124 TLS impersonation
        try:
            from curl_cffi import requests as cffi_requests

            def _cffi_req() -> Tuple[int, str]:
                resp = cffi_requests.get(
                    url,
                    headers=req_headers,
                    impersonate="chrome124",
                    timeout=t,
                )
                return resp.status_code, resp.text

            return await loop.run_in_executor(None, _cffi_req)
        except Exception as e:
            logger.debug("curl_cffi fetch failed for %s, falling back to httpx: %s", url, e)

        # 3. Async httpx fallback
        async with httpx.AsyncClient(timeout=t, follow_redirects=True) as client:
            resp = await client.get(url, headers=req_headers)
            return resp.status_code, resp.text

    async def fetch_post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[int, str]:
        """
        Performs resilient HTTP POST with Chrome 124 TLS impersonation or httpx.
        Returns (status_code, response_text).
        """
        t = timeout or self.timeout
        req_headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            req_headers.update(headers)

        loop = asyncio.get_running_loop()

        # 1. Synchronous curl_cffi in executor with Chrome 124 TLS impersonation
        try:
            from curl_cffi import requests as cffi_requests

            def _cffi_post() -> Tuple[int, str]:
                resp = cffi_requests.post(
                    url,
                    data=data,
                    json=json_data,
                    headers=req_headers,
                    impersonate="chrome124",
                    timeout=t,
                )
                return resp.status_code, resp.text

            return await loop.run_in_executor(None, _cffi_post)
        except Exception as e:
            logger.debug("curl_cffi post failed for %s, falling back to httpx: %s", url, e)

        # 2. Async httpx fallback
        async with httpx.AsyncClient(timeout=t, follow_redirects=True) as client:
            resp = await client.post(url, data=data, json=json_data, headers=req_headers)
            return resp.status_code, resp.text

    async def fetch_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Any]:
        """Fetches and parses JSON from the target URL."""
        import json

        try:
            status, text = await self.fetch_text(url, headers=headers, timeout=timeout)
            if status == 200 and text:
                return json.loads(text)
        except Exception as e:
            logger.debug("fetch_json error for %s: %s", url, e)
        return None

    def record_success(self, latency_ms: float) -> None:
        """Updates health metrics on successful operation."""
        self.health.total_requests += 1
        self.health.successful_requests += 1
        self.health.consecutive_failures = 0
        self.health.last_latency_ms = latency_ms
        self.health.is_open = False
        self.health.last_error = None

    def record_failure(self, error: Exception) -> None:
        """Updates health metrics on failure and triggers circuit breaker if needed."""
        self.health.total_requests += 1
        self.health.consecutive_failures += 1
        self.health.last_error = str(error)
        if self.health.consecutive_failures >= 5:
            self.health.is_open = True
            logger.warning("Circuit breaker opened for harvester %s after 5 failures", self.archetype)
