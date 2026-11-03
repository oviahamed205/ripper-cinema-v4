"""
tests.unit.test_scoring
~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for algorithmic stream scorer.
"""

from ripper.scoring import (
    ScoringCandidate,
    is_likely_trailer,
    calculate_source_score,
    rank_and_sort_candidates,
)


def test_trailer_detection():
    # Keyword detection
    assert is_likely_trailer("Movie Title Official Trailer 1080p", "1080p", 200000000) is True
    assert is_likely_trailer("Sample Clip 720p", "720p", 50000000) is True

    # Size-based detection for Movie (<800MB for 1080p movie)
    assert is_likely_trailer("Full Movie 1080p", "1080p", 100 * 1024 * 1024, is_series=False) is True

    # Legitimate full size movie
    assert is_likely_trailer("Full Movie 1080p", "1080p", 2500 * 1024 * 1024, is_series=False) is False


def test_calculate_source_score():
    c_trailer = ScoringCandidate(
        title="Movie Teaser Trailer",
        quality="1080p",
        size_bytes=50000000,
    )
    assert calculate_source_score(c_trailer) == -10000.0

    c_cached_1080p = ScoringCandidate(
        title="Movie.2024.1080p.WEBRip.x265",
        quality="1080p",
        size_bytes=2 * 1024 * 1024 * 1024,  # 2GB
        seeders=100,
        is_cached=True,
        codec="x265",
    )
    score1 = calculate_source_score(c_cached_1080p)
    assert score1 > 2000.0  # 1000 (1080p) + 1000 (cached) + seeders + codec


def test_rank_and_sort_candidates():
    c1 = ScoringCandidate(title="Movie.Trailer.1080p", quality="1080p", size_bytes=50000000)
    c2 = ScoringCandidate(title="Movie.1080p.Uncached", quality="1080p", size_bytes=2000000000, is_cached=False)
    c3 = ScoringCandidate(title="Movie.1080p.Cached.RD+", quality="1080p", size_bytes=2000000000, is_cached=True)

    ranked = rank_and_sort_candidates([c1, c2, c3])
    assert len(ranked) == 3
    # c3 should be rank 1 (cached), c2 rank 2 (uncached), c1 rank 3 (trailer)
    assert ranked[0][1].title == c3.title
    assert ranked[1][1].title == c2.title
    assert ranked[2][1].title == c1.title
