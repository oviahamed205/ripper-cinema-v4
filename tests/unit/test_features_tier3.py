"""
Unit tests for Tier 3 Enhancements:
1. File Integrity Checker (verify.py)
2. Watchlist & Favorites (watchlist.py)
3. Watch History & Analytics (history.py)
4. OpenSubtitles & Local Subtitle Discovery (subtitles.py)
5. YouTube Trailer (trailer.py)
6. OMDb Intel (omdb.py)
7. Media Player Subtitle Injection (player.py)
"""

import unittest
import tempfile
import pathlib
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from ripper.verify import verify_media_file
from ripper.watchlist import add_to_watchlist, get_watchlist, remove_from_watchlist
from ripper.history import add_to_history, get_history, get_stats, save_history
from ripper.subtitles import find_local_subtitle, search_subtitles
from ripper.trailer import find_trailer, open_trailer_in_browser
from ripper.omdb import fetch_omdb_details
from ripper.player import launch_video_stream_in_player


class TestTier3Features(unittest.IsolatedAsyncioTestCase):
    def test_verify_media_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. MKV valid
            mkv_f = Path(tmpdir) / "test.mkv"
            with open(mkv_f, "wb") as f:
                f.write(b"\x1a\x45\xdf\xa3" + b"\x00" * (1024 * 1024 + 10))
            valid, msg = verify_media_file(mkv_f)
            self.assertTrue(valid)
            self.assertIn("EBML", msg)

            # 2. HTML fake page
            html_f = Path(tmpdir) / "fake.mp4"
            with open(html_f, "wb") as f:
                f.write(b"<!DOCTYPE html><head></head>" + b"\x00" * (1024 * 1024 + 10))
            valid_h, msg_h = verify_media_file(html_f)
            self.assertFalse(valid_h)
            self.assertIn("HTML", msg_h)

    def test_watchlist_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ripper.watchlist.CONFIG_DIR", Path(tmpdir)), \
                 patch("ripper.watchlist.WATCHLIST_FILE", Path(tmpdir) / "watchlist.json"):
                add_to_watchlist("Spider-Man", "https://example.com/sm", "VegaMovies", "2021")
                wl = get_watchlist()
                self.assertEqual(len(wl), 1)
                self.assertEqual(wl[0]["title"], "Spider-Man")

                remove_from_watchlist("Spider-Man")
                self.assertEqual(len(get_watchlist()), 0)

    def test_history_and_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("ripper.history.CONFIG_DIR", Path(tmpdir)), \
                 patch("ripper.history.HISTORY_FILE" , Path(tmpdir) / "history.json"):
                add_to_history("Vikram", "https://example.com/vik", "1080p", "CineFreak")
                add_to_history("Leo", "https://example.com/leo", "4K", "CineFreak")
                hist = get_history()
                self.assertEqual(len(hist), 2)

                stats = get_stats()
                self.assertEqual(stats["total_streams"], 2)
                self.assertEqual(stats["top_source_site"], "CineFreak")

    def test_find_local_subtitle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            srt_f = Path(tmpdir) / "SpiderMan.No.Way.Home.2021.1080p.srt"
            srt_f.write_text("1 00:00:00 -> 00:00:02 Hello")
            found = find_local_subtitle("Spider-Man No Way Home", current_dir=Path(tmpdir))
            self.assertIsNotNone(found)
            self.assertEqual(found.name, srt_f.name)

    async def test_trailer_direct_fallback(self):
        t = await find_trailer("Oppenheimer", "2023")
        self.assertIn("youtube.com", t["trailer_url"])
