"""
tests.unit.test_png_stripper
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for fake-PNG wrapper detection and MPEG-TS chunk stripping.
"""

from ripper.proxy.png_stripper import (
    PNG_SIG,
    IEND_MARKER,
    is_fake_png_stream,
    strip_fake_png_header,
)


def test_is_fake_png_stream():
    fake_png = PNG_SIG + b"some_chunk_data"
    assert is_fake_png_stream(fake_png) is True

    clean_ts = b"\x47\x40\x00\x10" + b"ts_packet_payload"
    assert is_fake_png_stream(clean_ts) is False
    assert is_fake_png_stream(b"") is False


def test_strip_fake_png_header():
    # Construct realistic fake PNG wrapper:
    # \x89PNG\r\n\x1a\n ... IEND<4-byte-crc> + REAL_VIDEO_DATA
    raw_video = b"\x47\x40\x11\x10" + b"REAL_MPEG_TS_STREAM_PAYLOAD_12345"
    crc_dummy = b"\x12\x34\x56\x78"
    fake_wrapper = PNG_SIG + b"fake_ihdr_chunk" + IEND_MARKER + crc_dummy + raw_video

    stripped = strip_fake_png_header(fake_wrapper)
    assert stripped == raw_video

    # Untouched for clean stream
    assert strip_fake_png_header(raw_video) == raw_video
    assert strip_fake_png_header(b"") == b""
