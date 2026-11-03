"""
tests.unit.test_downloader_sanitize
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for Windows reserved filename sanitization in downloader.
"""

from ripper.downloader.engine import sanitize_filename


def test_sanitize_windows_reserved_names():
    assert sanitize_filename("CON.mp4") == "CON_.mp4"
    assert sanitize_filename("prn.mkv") == "prn_.mkv"
    assert sanitize_filename("AUX.mp4") == "AUX_.mp4"
    assert sanitize_filename("NUL.avi") == "NUL_.avi"
    assert sanitize_filename("COM1.mp4") == "COM1_.mp4"
    assert sanitize_filename("LPT9.ts") == "LPT9_.ts"


def test_sanitize_illegal_characters():
    raw = 'Movie: Title? <Part 1> | "2024" * Edition.mp4'
    clean = sanitize_filename(raw)
    assert ":" not in clean
    assert "?" not in clean
    assert "<" not in clean
    assert ">" not in clean
    assert "|" not in clean
    assert '"' not in clean
    assert "*" not in clean
    assert clean.endswith(".mp4")
