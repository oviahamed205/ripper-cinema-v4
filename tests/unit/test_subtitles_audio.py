"""
Unit tests for Subtitle Engine, Multi-Language Audio Selector, and Charset Normalization.
"""
import unittest
import tempfile
from pathlib import Path

from ripper.subtitles.engine import SubtitleEngine, normalize_subtitle_encoding
from ripper.subtitles.audio_tracks import (
    AudioTrackInfo,
    parse_audio_languages_from_title,
    LANGUAGE_MAP,
)


class TestSubtitleAndAudioEngine(unittest.TestCase):

    def test_audio_track_parsing_dual_audio(self):
        title = "Deadpool.and.Wolverine.2024.1080p.Dual.Audio.Hindi.English.x265"
        tracks = parse_audio_languages_from_title(title)
        self.assertGreaterEqual(len(tracks), 2)
        lang_codes = [t.language_code for t in tracks]
        self.assertIn("hi", lang_codes)
        self.assertIn("en", lang_codes)

    def test_audio_track_parsing_multi_audio(self):
        title = "Kalki.2898.AD.2024.Hindi.Tamil.Telugu.Malayalam.2160p.HEVC"
        tracks = parse_audio_languages_from_title(title)
        lang_codes = [t.language_code for t in tracks]
        self.assertIn("hi", lang_codes)
        self.assertIn("ta", lang_codes)
        self.assertIn("te", lang_codes)
        self.assertIn("ml", lang_codes)

    def test_charset_normalization_utf8_bom(self):
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            # Write text with UTF-8 BOM
            bom_content = "\ufeff1\n00:00:01,000 --> 00:00:03,000\nHello World\n".encode("utf-8-sig")
            f.write(bom_content)
            temp_path = Path(f.name)

        try:
            res = normalize_subtitle_encoding(temp_path)
            self.assertTrue(res)
            # Re-read and check that BOM is stripped
            raw = temp_path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"Hello World", raw)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_charset_normalization_cp1252(self):
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            # Write accented word in Windows-1252 (e.g. café -> 0xe9)
            cp1252_content = b"1\n00:00:01,000 --> 00:00:03,000\nCaf\xe9\n"
            f.write(cp1252_content)
            temp_path = Path(f.name)

        try:
            res = normalize_subtitle_encoding(temp_path)
            self.assertTrue(res)
            content_str = temp_path.read_text(encoding="utf-8")
            self.assertIn("Café", content_str)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_subtitle_engine_local_discovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            sub_file = tmp_path / "Inception_2010_en.srt"
            sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nDream\n", encoding="utf-8")

            engine = SubtitleEngine(download_dir=tmp_path)
            found = engine.find_local_subtitle("Inception 2010")
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "Inception_2010_en.srt")


if __name__ == "__main__":
    unittest.main()
