"""
Verify file integrity by checking magic bytes, container headers, and filesize.
"""

import os
from pathlib import Path
from typing import Tuple

MP4_FTYP_OFFSET = 4
MKV_EBML_START = b"\x1a\x45\xdf\xa3"
ZIP_START = b"PK\x03\x04"


def verify_media_file(file_path: Path) -> Tuple[bool, str]:
    """
    Verify downloaded media file is not corrupted, empty, or an HTML ad page.
    Returns (success: bool, message: str).
    """
    p = Path(file_path)
    if not p.exists():
        return False, "File does not exist."

    size = p.stat().st_size
    if size < 1024 * 1024:
        return False, f"File too small ({file_path.name} - {size / 1024:.1f} KB), likely corrupted or HTML snippet."

    try:
        with open(p, "rb") as ffile:
            header = ffile.read(32)

            if header.startswith(b"\x1a\x45\xdf\xa3"):
                return True, "Verified MKV / WebM (EBML Container)"
            if b"ftyp" in header:
                return True, "Verified MP4 / MOV (ISO Base Media)"
            if header.startswith(b"RIFF") and len(header) >= 12 and b"AVI " in header[8:12]:
                return True, "Verified AVI (RIFF Container)"
            if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
                return True, "Verified ZIP / Archive Container"

            h_lower = header.lower()
            if b"<!doctype" in h_lower or b"<html" in h_lower:
                return False, "CORRUPT: File is an HTML web page instead of a real video."

            return True, f"Valid Binary Media File ({size / (1024 * 1024):.1f} MB)"
    except Exception as e:
        return False, f"Read Error: {e}"
