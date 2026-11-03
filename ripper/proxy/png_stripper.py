"""
ripper.proxy.png_stripper
~~~~~~~~~~~~~~~~~~~~~~~~~

De-obfuscator for video streams wrapped in fake PNG headers.
Ported from lobster/internal/hlsproxy/hlsproxy.go:
- Detects fake PNG signature: \\x89PNG\\r\\n\\x1a\\n (used by megaplay/ibyteimg to disguise MPEG-TS video chunks)
- Locates IEND chunk marker and strips preceding envelope (+ 4-byte CRC)
- Returns pure MPEG-TS / HLS video payload ready for player demuxers.
"""

PNG_SIG = b"\x89PNG\r\n\x1a\n"
IEND_MARKER = b"IEND"


def is_fake_png_stream(data: bytes) -> bool:
    """Check if byte payload begins with PNG magic signature."""
    return data.startswith(PNG_SIG)


def strip_fake_png_header(data: bytes) -> bytes:
    """
    Remove fake-PNG wrapper (\\x89PNG...IEND<crc>) so media players can demux the true MPEG-TS stream.
    If payload is not wrapped in a fake PNG, returns untouched bytes.
    """
    if not data or not is_fake_png_stream(data):
        return data

    iend_pos = data.find(IEND_MARKER)
    if iend_pos != -1 and iend_pos + 8 <= len(data):
        # IEND is 4 bytes + 4 bytes CRC = 8 bytes total
        return data[iend_pos + 8 :]

    return data
