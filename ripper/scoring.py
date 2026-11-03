"""
ripper.scoring
~~~~~~~~~~~~~~

Algorithmic Stream Quality and Recommendation Scorer.
Ported from miru/src/api/source_scoring.rs:
- Mathematical recommendation scoring formula
- High-penalty trailer detection and removal (-10,000 pts)
- Resolution, codec, and audio weighting (REMUX, Atmos, HEVC, AV1)
- Debrid instant-cache bonus (+1,000 pts)
- Logarithmic seeder bonus: 50 * log2(seeders + 1)
- Exponential size penalty: -80 * (size_gb ^ 1.5)
"""

from __future__ import annotations

import re
import math
from typing import List, Optional, Any, Dict
from dataclasses import dataclass


TRAILER_KEYWORDS_RE = re.compile(
    r"(?i)\b(trailer|promo|sample|preview|clip|extra|bonus|teaser|opening|ending|op|ed)\b"
)


@dataclass
class ScoringCandidate:
    title: str
    quality: str
    size_bytes: int = 0
    seeders: int = 0
    is_cached: bool = False
    codec: Optional[str] = None
    audio: Optional[str] = None
    is_series: bool = False
    raw_item: Optional[Any] = None


def is_likely_trailer(title: str, quality: str, size_bytes: int, is_series: bool = False) -> bool:
    """Detect if title is a sample/trailer based on keywords and size thresholds."""
    title_lower = title.lower()
    if TRAILER_KEYWORDS_RE.search(title_lower):
        return True

    if size_bytes <= 0:
        return False

    size_mb = size_bytes / (1024.0 * 1024.0)
    q_lower = quality.lower()

    if is_series:
        # TV episode thresholds
        if "2160p" in q_lower or "4k" in q_lower:
            return size_mb < 400.0
        elif "1080p" in q_lower:
            return size_mb < 150.0
        elif "720p" in q_lower:
            return size_mb < 80.0
        else:
            return size_mb < 30.0
    else:
        # Movie thresholds
        if "2160p" in q_lower or "4k" in q_lower:
            return size_mb < 2000.0
        elif "1080p" in q_lower:
            return size_mb < 800.0
        elif "720p" in q_lower:
            return size_mb < 400.0
        else:
            return size_mb < 150.0


def calculate_source_score(candidate: ScoringCandidate) -> float:
    """
    Calculate numerical ranking score for candidate media stream.
    Higher scores represent better stream quality and reliability.
    """
    # 1. Massive trailer penalty
    if is_likely_trailer(candidate.title, candidate.quality, candidate.size_bytes, candidate.is_series):
        return -10000.0

    score = 0.0
    q = candidate.quality.lower()

    # 2. Resolution weighting
    if "1080p" in q:
        score += 1000.0
    elif "720p" in q:
        score += 800.0
    elif "2160p" in q or "4k" in q:
        score += 600.0  # 4K is pristine but penalized if bandwidth is constrained
    else:
        score += 400.0

    # 3. Real-Debrid / CDN instant-cache bonus
    if candidate.is_cached:
        score += 1000.0

    # 4. Logarithmic seeder bonus
    if candidate.seeders > 0:
        score += math.log2(candidate.seeders + 1) * 50.0

    # 5. Exponential size penalty (guards against massive uncompressed bloated files)
    if candidate.size_bytes > 0:
        size_gb = candidate.size_bytes / (1024.0 * 1024.0 * 1024.0)
        # -(size_gb ^ 1.5) * 80
        score -= (size_gb ** 1.5) * 80.0

    # 6. Premium codec & audio bonuses
    title_lower = candidate.title.lower()
    codec_lower = (candidate.codec or "").lower()
    audio_lower = (candidate.audio or "").lower()

    if "remux" in title_lower:
        score += 300.0

    if any(c in codec_lower or c in title_lower for c in ("hevc", "x265", "av1", "10bit")):
        score += 150.0

    if any(a in audio_lower or a in title_lower for a in ("atmos", "truehd")):
        score += 200.0
    elif "dts-hd" in audio_lower or "dts-hd" in title_lower:
        score += 150.0

    return score


def rank_and_sort_candidates(candidates: List[ScoringCandidate]) -> List[Tuple[float, ScoringCandidate]]:
    """Score, filter out trailers, and sort candidates in descending order."""
    scored = []
    for c in candidates:
        s = calculate_source_score(c)
        scored.append((s, c))
    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored
