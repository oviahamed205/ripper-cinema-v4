"""
Raw Directory Index Crawler for Apache/Nginx/Lighttpd/IIS open directories.
Extracts direct media files (.mkv, .mp4, .zip, .rar) from directory index pages.
"""

from __future__ import annotations

import html as html_lib
import re
import urllib.parse
from typing import List, Set, Tuple

from bs4 import BeautifulSoup

MEDIA_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".flv", ".webm", ".ts", ".m4v", ".wmv",
    ".zip", ".rar", ".7z", ".iso", ".srt", ".ass",
}

_COMPOUND_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz")

_STRONG_INDEX_MARKERS = (
    "index of /",
    "<title>index of",
    "directory listing for",
    "[to parent directory]",
    "directory listing of",
)

_PARENT_NAMES = {
    "parent directory",
    "..",
    "../",
    "./",
    "[to parent directory]",
}


def _path_has_media_suffix(path: str) -> bool:
    lowered = (path or "").lower()
    if any(lowered.endswith(ext) for ext in _COMPOUND_EXTENSIONS):
        return True
    return any(lowered.endswith(ext) for ext in MEDIA_EXTENSIONS)


def is_directory_index(html_content: str) -> bool:
    """Check if HTML content is an Apache/Nginx/Lighttpd/IIS directory listing."""
    if not html_content or len(html_content) < 50:
        return False
    sample = html_content[:4000].lower()
    if any(marker in sample for marker in _STRONG_INDEX_MARKERS):
        return True
    if "parent directory" in sample and ("<pre>" in sample or "last modified" in sample):
        return True
    if "name</a>" in sample and "last modified" in sample and "size" in sample:
        return True
    return False


def parse_directory_index(html_content: str, base_url: str) -> List[Tuple[str, str]]:
    """
    Parse raw directory index and return list of (clean_filename, full_download_url).
    """
    if not is_directory_index(html_content):
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    candidates: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.startswith("?") or href in ("../", "./", "/"):
            continue
        if any(token in href for token in ("?C=", "?O=", "?S=", "?N=", "?M=", "?D=")):
            continue

        text = html_lib.unescape((anchor.get_text() or "").strip())
        if text.lower() in _PARENT_NAMES:
            continue

        full_url = urllib.parse.urljoin(base_url, href)
        try:
            parsed = urllib.parse.urlparse(full_url)
        except Exception:
            continue
        if parsed.scheme not in ("http", "https", "ftp"):
            continue
        if parsed.path.endswith("/"):
            continue

        path_unquoted = urllib.parse.unquote(parsed.path)
        if not _path_has_media_suffix(path_unquoted):
            continue
        if full_url in seen:
            continue

        seen.add(full_url)
        if text and _path_has_media_suffix(text):
            filename = text
        else:
            filename = path_unquoted.rstrip("/").split("/")[-1] or "download_file"
        filename = urllib.parse.unquote(filename)
        candidates.append((filename, full_url))

    return candidates
