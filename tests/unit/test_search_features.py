"""
Unit tests for site search registry, language filters, TV season parsing, and export functions.
"""

import tempfile
import unittest
from pathlib import Path
from ripper.search import resolve_site_names, normalize_title_for_grouping, group_duplicate_results, SearchResultItem
from ripper.media import parse_movie_title_header, detect_language, extract_season_episode
from ripper.batch import export_search_results


class TestSearchFeatures(unittest.TestCase):
    def test_resolve_site_names(self):
        expected_all = [
            "moviebox", "fourkhdhub", "torrentio",
            "vegamovies", "katmoviehd", "cinefreak", "olamovies", "kmmovies", "hdhub4u",
            "fmoviess", "movie4k", "lookmovie", "bollypro", "7starhd", "hindilinks4u",
            "worldfree4u", "9xmovie", "downloadhub", "movienz", "filmsur", "filmshd",
            "mp4gana", "local"
        ]
        self.assertEqual(resolve_site_names("all"), expected_all)
        self.assertEqual(resolve_site_names("vega,kat"), ["vegamovies", "katmoviehd"])
        self.assertEqual(resolve_site_names("cinefreak,ola,hdhub"), ["cinefreak", "olamovies", "hdhub4u"])
        self.assertEqual(resolve_site_names("mb,4khdhub,torrentio"), ["moviebox", "fourkhdhub", "torrentio"])

    def test_parse_movie_title_header_extended(self):
        title = "Vikram (2022) [Tamil + Telugu + Hindi] 1080p HQ 10Bit [3.5 GB]"
        m_name, audio, codec, quality, size, s, ep = parse_movie_title_header(title)
        self.assertIn("Vikram", m_name)
        self.assertIn("Tamil", audio)
        self.assertEqual(quality, "1080P")
        self.assertEqual(size, "3.5 GB")

    def test_extract_season_episode(self):
        s, ep = extract_season_episode("Loki Season 2 Episode 4 (2023) 1080p")
        self.assertEqual(s, 2)
        self.assertEqual(ep, 4)

        s2, ep2 = extract_season_episode("Arcane S01E09 [Multi Audio]")
        self.assertEqual(s2, 1)
        self.assertEqual(ep2, 9)

    def test_detect_language(self):
        self.assertEqual(detect_language("Leo (2023) [Tamil + Hindi] 1080p"), "Tamil")
        self.assertEqual(detect_language("Pushpa 2 [Telugu + Hindi] 720p"), "Telugu")
        self.assertEqual(detect_language("Manjummel Boys [Malayalam (Original)]"), "Malayalam")

    def test_export_search_results(self):
        items = [
            SearchResultItem(
                site_name="CineFreak",
                title="Spider-Man: Brand New Day",
                url="https://cinefreak.net/spider-man",
                year="2026",
                quality_tags="1080p HD, 720p HEVC",
                language="Hindi",
            )
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_p = Path(tmpdir) / "results.json"
            csv_p = Path(tmpdir) / "results.csv"
            md_p = Path(tmpdir) / "results.md"

            export_search_results(items, json_p)
            export_search_results(items, csv_p)
            export_search_results(items, md_p)

            self.assertTrue(json_p.exists() and json_p.stat().st_size > 0)
            self.assertTrue(csv_p.exists() and csv_p.stat().st_size > 0)
            self.assertTrue(md_p.exists() and md_p.stat().st_size > 0)

    def test_relevance_scoring_and_fuzzy(self):
        from ripper.search import score_relevance, fuzzy_filter_results, filter_by_year, extract_year_from_query

        item1 = SearchResultItem(
            site_name="VegaMovies",
            title="Spider-Man: No Way Home",
            url="https://vegamovies.futbol/spiderman",
            year="2021",
            quality_tags="4K UHD, 1080p, HEVC",
        )
        item2 = SearchResultItem(
            site_name="CineFreak",
            title="Iron Man (2008)",
            url="https://cinefreak.net/iron-man",
            year="2008",
            quality_tags="720p",
        )

        score1 = score_relevance(item1, "Spider-Man 2021")
        score2 = score_relevance(item2, "Spider-Man 2021")
        self.assertGreater(score1, score2)

        # Test fuzzy filter
        filtered = fuzzy_filter_results([item1, item2], "spiderman")
        self.assertIn(item1, filtered)

        # Test year extractor & filter
        self.assertEqual(extract_year_from_query("spider-man 2021"), "2021")
        year_filtered = filter_by_year([item1, item2], "2021")
        self.assertIn(item1, year_filtered)
        self.assertNotIn(item2, year_filtered)

