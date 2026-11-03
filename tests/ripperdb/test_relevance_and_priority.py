"""
tests.ripperdb.test_relevance_and_priority
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for title relevance, year mismatch gating, non-streamer domain exclusion,
provider prioritization, and headless solver cancellation safety.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ripper.ripperdb.cache import RipperDBCache
from ripper.ripperdb.harvesters.base import (
    extract_title_and_year,
    is_title_relevant,
)
from ripper.ripperdb.harvesters.dispatcher import (
    HarvesterDispatcher,
    EXCLUDED_NON_STREAMER_DOMAINS,
    VERIFIED_TIER_1_PROVIDERS,
)
from ripper.bypass.ladder import BypassLadder
from ripper.bypass.headless import HeadlessSolver


def test_extract_title_and_year():
    title, year = extract_title_and_year("The End of Oak Street (2026)")
    assert title == "The End of Oak Street"
    assert year == 2026

    title, year = extract_title_and_year("Interstellar 2014")
    assert title == "Interstellar"
    assert year == 2014

    title, year = extract_title_and_year("Breaking Bad S01E01")
    assert title == "Breaking Bad S01E01"
    assert year is None

    title, year = extract_title_and_year("Dune: Part Two (2024) [1080p]")
    assert title == "Dune: Part Two"
    assert year == 2024


def test_is_title_relevant_rejection_of_unrelated_popular_movies():
    query = "The End of Oak Street"
    target_year = 2026

    # Unrelated titles scraped from azseries recommendation lists MUST BE REJECTED
    assert not is_title_relevant("Get the Grift", query, query_year=target_year)
    assert not is_title_relevant("Yes Day", query, query_year=target_year)
    assert not is_title_relevant("Tom Clancy's Without Remorse", query, query_year=target_year)
    assert not is_title_relevant("A Quiet Place Part II", query, query_year=target_year)
    assert not is_title_relevant("The Conjuring: The Devil Made Me Do It", query, query_year=target_year)
    assert not is_title_relevant("In the Heights", query, query_year=target_year)
    assert not is_title_relevant("Cruella", query, query_year=target_year)
    assert not is_title_relevant("Luca", query, query_year=target_year)


def test_is_title_relevant_acceptance_of_valid_matches():
    query = "The End of Oak Street"
    target_year = 2026

    assert is_title_relevant("The End of Oak Street (2026)", query, query_year=target_year)
    assert is_title_relevant("The End of Oak Street 2026 1080p WEB-DL", query, query_year=target_year)
    assert is_title_relevant("The End of Oak Street (Movie)", query, query_year=target_year)
    assert is_title_relevant("The End of Oak Street", query, query_year=target_year)


def test_is_title_relevant_year_mismatch_gating():
    query = "Interstellar"
    target_year = 2014

    # Matches year or +/- 1
    assert is_title_relevant("Interstellar (2014)", query, query_year=target_year)
    assert is_title_relevant("Interstellar 2015 Remaster", query, query_year=target_year)

    # Rejects blatant year mismatch (> 1 year diff)
    assert not is_title_relevant("Interstellar (2024)", query, query_year=target_year)
    assert not is_title_relevant("Interstellar 1980", query, query_year=target_year)


def test_provider_prioritization_and_exclusion(tmp_path):
    cache = RipperDBCache(db_path=str(tmp_path / "test_prio.db"))
    dispatcher = HarvesterDispatcher(cache_engine=cache)

    # Add various providers: excluded non-streamers, tier 1, and regular
    cache.upsert_provider("animecharactersdatabase", "Anime Characters Database", "embed", "https://acdb.com")
    cache.upsert_provider("arte", "Arte TV", "embed", "https://arte.tv")
    cache.upsert_provider("7plus", "7 Plus", "embed", "https://7plus.com.au")
    cache.upsert_provider("random_low_prov", "Random Low", "embed", "https://randomlow.com")
    cache.upsert_provider("yts", "YTS Torrents", "torrent", "https://yts.mx")
    cache.upsert_provider("katmoviehd", "KatmovieHD", "embed", "https://katmoviehd.to")
    cache.upsert_provider("vegamovies", "VegaMovies", "embed", "https://vegamovies.to")

    prioritized = dispatcher.get_prioritized_providers(max_providers=10)
    p_ids = [p["id"] for p in prioritized]

    # Excluded domains must NOT be in prioritized list
    assert "animecharactersdatabase" not in p_ids
    assert "arte" not in p_ids
    assert "7plus" not in p_ids

    # Tier 1 providers must come before random_low_prov
    assert "yts" in p_ids
    assert "katmoviehd" in p_ids
    assert "vegamovies" in p_ids
    random_idx = p_ids.index("random_low_prov")
    yts_idx = p_ids.index("yts")
    assert yts_idx < random_idx


@pytest.mark.asyncio
async def test_bypass_ladder_allow_headless_flag():
    ladder = BypassLadder()
    with patch("ripper.bypass.curl_client.HAS_CURL_CFFI", True), \
         patch.object(ladder.curl, "get", new_callable=AsyncMock) as mock_curl, \
         patch.object(ladder.companion, "solve", new_callable=AsyncMock) as mock_companion, \
         patch.object(ladder.headless, "solve", new_callable=AsyncMock) as mock_headless:

        # Mock Level 0/1 and Level 2 failing with 403
        mock_curl.return_value = (403, "Cloudflare challenge cf-ray", {"cf-ray": "123"}, {})
        mock_companion.return_value = None

        # When allow_headless=False, headless solver must NEVER be called
        status, html, headers = await ladder.fetch("https://protected.test", allow_headless=False)
        assert status == 403
        mock_headless.solve.assert_not_called()


@pytest.mark.asyncio
async def test_headless_solver_shielded_cancellation():
    solver = HeadlessSolver()

    # Simulate cancellation during headless solve
    with patch("playwright.async_api.async_playwright") as mock_pw_ctx:
        mock_pw = AsyncMock()
        mock_browser = AsyncMock()
        mock_pw_ctx.return_value.start = AsyncMock(return_value=mock_pw)
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(side_effect=asyncio.CancelledError("Cancelled"))

        with pytest.raises(asyncio.CancelledError):
            await solver.solve("https://test.com")

        # Browser and playwright should be closed cleanly
        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()
