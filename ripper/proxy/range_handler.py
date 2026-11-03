"""
HTTP 206 Partial Content & Range Request Handler for Media Streaming.
Enables instant scrubbing, seeking, and pausing in PotPlayer/VLC without buffering.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


def parse_range_header(range_header: Optional[str], total_length: Optional[int] = None) -> Optional[Tuple[int, Optional[int]]]:
    """
    Parse an HTTP Range header (e.g., 'bytes=1048576-2097152' or 'bytes=1048576-').
    Returns (start_byte, end_byte).
    """
    if not range_header:
        return None
    match = re.search(r"bytes=(\d+)-(\d*)", range_header.strip())
    if not match:
        return None
    start = int(match.group(1))
    end_str = match.group(2)
    end = int(end_str) if end_str else None
    if total_length is not None and end is not None:
        end = min(end, total_length - 1)
    return start, end


def format_content_range(start: int, end: int, total: int) -> str:
    """Format HTTP Content-Range header: bytes <start>-<end>/<total>."""
    return f"bytes {start}-{end}/{total}"