"""
OpenSubtitles API & Local Subtitle Auto-Discovery for unshorten-cli.
Auto-finds, downloads, and loads .srt/.ass subtitles directly into PotPlayer / VLC.
"""

import os
import re
import httpx
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from ..config import get_config_value

SUBTITLES_DIR = Path.home() / "Downloads" / "Subtitles"
OPENS_BASE_URL = "https://api.opensubtitles.com/api/v1"


async def search_subtitles(
    title: str,
    year: Optional[str] = None,
    languages: str = "en,hi",
    api_key: Optional[str] = None,
    timeout: float = 5.0,
) -> List[Dict[str, Any]]:
    """Search OpenSubtitles API v1 for matching subtitles."""
    key = api_key or get_config_value("opensubtitles_api_key", "")
    results = []
    try:
        params = {"query": title, "languages": languages}
        if year:
            params["year"] = year

        headers = {"User-Agent": "unshorten-cli v3.0", "Accept": "application/json"}
        if key:
            headers["Api-Key"] = key

        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(f"{OPENS_BASE_URL}/subtitles", params=params, headers=headers)
            if resp.status_code != 200:
                return []

            data = resp.json()
            for item in data.get("data", []):
                attr = item.get("attributes", {})
                files = attr.get("files", [])
                file_id = files[0].get("file_id") if files else None
                file_name = files[0].get("file_name") if files else attr.get("release")

                results.append({
                    "subtitle_id": file_id,
                    "file_name": file_name or f"{title}.srt",
                    "language": attr.get("language"),
                    "rating": attr.get("ratings", 0),
                    "download_count": attr.get("download_count", 0),
                    "download_url": attr.get("url"),
                })
    except Exception:
        pass
    return results


def find_local_subtitle(video_name_or_title: str, current_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Search for a local .srt or .ass subtitle file matching the movie title or filename.
    Searches current working directory, video folder, and ~/Downloads/Subtitles/.
    """
    clean_q = re.sub(r"[^a-z0-9]+", " ", video_name_or_title.lower()).strip()
    keywords = [w for w in clean_q.split() if len(w) > 2]

    dirs_to_search = [SUBTITLES_DIR.expanduser(), Path.cwd()]
    if current_dir:
        dirs_to_search.insert(0, Path(current_dir))

    for d in dirs_to_search:
        if not d.exists():
            continue
        for f in (d.iterdir() if hasattr(d, "iterdir") else []):
            if f.suffix.lower() in (".srt", ".ass", ".vtt"):
                fname = f.stem.lower()
                if any(w in fname for w in keywords):
                    return f

    return None


async def download_subtitle_file(
    file_id_or_url: str,
    output_filename: str,
    api_key: Optional[str] = None,
    timeout: float = 8.0,
) -> Optional[Path]:
    """Download .srt subtitle file to ~/Downloads/Subtitles/."""
    SUBTITLES_DIR.expanduser().mkdir(parents=True, exist_ok=True)
    dest_path = SUBTITLES_DIR.expanduser() / output_filename

    key = api_key or get_config_value("opensubtitles_api_key", "")
    headers = {"User-Agent": "unshorten-cli v3.0"}
    if key:
        headers["Api-Key"] = key

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True) as client:
            if file_id_or_url.startswith("http"):
                resp = await client.get(file_id_or_url, headers=headers)
            else:
                # OpenSubtitles download endpoint
                resp = await client.post(
                    f"{OPENS_BASE_URL}/download",
                    json={"file_id": int(file_id_or_url)},
                    headers=headers,
                )
                if resp.status_code == 200:
                    link = resp.json().get("link")
                    if link:
                        resp = await client.get(link)

            if resp.status_code == 200 and len(resp.content) > 10:
                with open(dest_path, "wb") as f:
                    f.write(resp.content)
                return dest_path
    except Exception:
        pass
    return None


async def auto_fetch_and_load_subtitle(
    title: str,
    year: Optional[str] = None,
    languages: str = "en,hi",
) -> Optional[Path]:
    """
    Find local subtitle or automatically fetch best match from OpenSubtitles.
    Returns Path to ready .srt file or None.
    """
    # 1. Check local files first
    local = find_local_subtitle(title)
    if local:
        return local

    # 2. Search OpenSubtitles if API key exists
    key = get_config_value("opensubtitles_api_key", "")
    if key:
        subs = await search_subtitles(title, year=year, languages=languages, api_key=key)
        if subs and subs[0].get("subtitle_id"):
            safe_name = f"{re.sub(r'[^a-zA-Z0-9]', '_', title)}_{subs[0].get('language', 'en')}.srt"
            downloaded = await download_subtitle_file(
                str(subs[0]["subtitle_id"]),
                output_filename=safe_name,
                api_key=key,
            )
            if downloaded:
                return downloaded

    return None

