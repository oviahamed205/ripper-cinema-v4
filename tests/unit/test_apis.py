"""
Unit tests for Metadata API Brain Layer (TMDB, TVmaze, AniList) and Config Manager.
"""

import unittest
import tempfile
import pathlib
from unittest.mock import patch, AsyncMock, MagicMock
from ripper.config import load_config, save_config, get_config_value, set_config_value
from ripper.apis import search_tvmaze, search_anilist, search_tmdb, unified_metadata_search


class TestMetadataAPIs(unittest.IsolatedAsyncioTestCase):
    def test_config_load_and_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ripper.config.CONFIG_DIR", pathlib.Path(tmpdir)), \
                 patch("ripper.config.CONFIG_FILE", pathlib.Path(tmpdir) / "config.json"):
                set_config_value("tmdb_api_key", "test1234")
                self.assertEqual(get_config_value("tmdb_api_key"), "test1234")

    @patch("httpx.AsyncClient.get")
    async def test_search_tvmaze(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"show": {"id": 169, "name": "Breaking Bad", "premiered": "2008-01-20", "rating": {"average": 9.5}, "genres": ["Drama", "Crime"]}}
        ]
        mock_get.return_value = mock_resp
        res = await search_tvmaze("breaking bad")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["canonical_title"], "Breaking Bad")
        self.assertEqual(res[0]["year"], "2008")

    @patch("httpx.AsyncClient.post")
    async def test_search_anilist(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"Page": {"media": [{"id": 16498, "title": {"english": "Attack on Titan"}, "startDate": {"year": 2013}, "format": "TV", "averageScore": 86}]}}
        }
        mock_post.return_value = mock_resp
        res = await search_anilist("attack on titan")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["canonical_title"], "Attack on Titan")
        self.assertEqual(res[0]["year"], "2013")

