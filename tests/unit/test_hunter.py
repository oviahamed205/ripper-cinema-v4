"""
Unit test suite for The Hunter Engine (Site Hunter & Movie Hunter).
"""
import unittest
from unittest.mock import patch, AsyncMock
import sys
import asyncio

sys.path.insert(0, r"C:\Users\M Y T H O S\.gemini\antigravity\scratch\unshorten-cli")

from ripper.hunter.site_hunter import SiteHunter, DiscoveredSite
from ripper.hunter.movie_hunter import MovieHunter, HuntedMovie
from ripper.hunter.link_verifier import LinkVerificationResult
from ripper.hunter.fingerprint import fingerprint_site
from ripper.hunter.auto_scraper import auto_search_site


class TestHunterEngine(unittest.TestCase):

    def test_discovered_site_initialization(self):
        site = DiscoveredSite(
            domain="cinefreak.net",
            url="https://cinefreak.net",
            is_alive=True,
            is_wordpress=True,
            scraper_type="wordpress_api",
            content_score=95.0,
            reliability_score=90.0,
        )
        self.assertEqual(site.domain, "cinefreak.net")
        self.assertTrue(site.is_alive)
        self.assertTrue(site.is_wordpress)

    def test_site_hunter_default_sites(self):
        sh = SiteHunter()
        active = sh.get_all_active_sites()
        self.assertGreaterEqual(len(active), 6)
        domains = [s.domain for s in active]
        self.assertIn("cinefreak.net", domains)
        self.assertIn("kmmovies.pics", domains)
        self.assertIn("vegamovies.ph", domains)

    def test_movie_hunter_fuzzy_filter(self):
        sh = SiteHunter()
        mh = MovieHunter(sh)

        raw = [
            HuntedMovie(title="Spider-Man: Brand New Day (2026)", quality="1080P", source_site="cinefreak.net"),
            HuntedMovie(title="Spider Man 2 (2004) BluRay", quality="720P", source_site="kmmovies.pics"),
            HuntedMovie(title="Inception (2010) Dual Audio", quality="1080P", source_site="vegamovies.ph"),
        ]

        filtered = mh._fuzzy_filter(raw, "Spider-Man")
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all("spider" in m.title.lower() for m in filtered))

    def test_movie_hunter_deduplication(self):
        sh = SiteHunter()
        mh = MovieHunter(sh)

        raw = [
            HuntedMovie(title="Spider-Man: Brand New Day (2026)", quality="1080P", source_site="cinefreak.net"),
            HuntedMovie(title="Spider-Man Brand New Day 2026", quality="1080P", source_site="kmmovies.pics"),
            HuntedMovie(title="Spider-Man 2002", quality="720P", source_site="vegamovies.ph"),
        ]

        deduped = mh._deduplicate(raw)
        self.assertEqual(len(deduped), 2)

    def test_movie_hunter_score_calculation(self):
        sh = SiteHunter()
        mh = MovieHunter(sh)

        high_quality = HuntedMovie(
            title="Spider-Man",
            quality="2160P",
            is_verified=True,
            size="16.98 GB",
            audio="Hindi & English",
        )
        low_quality = HuntedMovie(
            title="Spider-Man",
            quality="480P",
            is_verified=False,
            size="Unknown",
            audio="Unknown",
        )

        score_hq = mh._calculate_score(high_quality)
        score_lq = mh._calculate_score(low_quality)

        self.assertGreater(score_hq, score_lq)
        self.assertEqual(score_hq, 100.0)


if __name__ == "__main__":
    unittest.main()
