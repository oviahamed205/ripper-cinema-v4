"""
ripper.subtitles.engine
~~~~~~~~~~~~~~~~~~~~~~~

High-performance subtitle search, auto-download, charset normalization,
and multi-language subtitle selector for ripper.
Supports:
- OpenSubtitles.com REST API v1
- SubDL API & Multi-Language provider
- Local fuzzy directory matcher (~/Downloads/Subtitles, CWD)
- Auto-converts CP1252 / ISO-8859 / UTF-16 to clean UTF-8 (strips BOM)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from ..config import get_config_value

logger = logging.getLogger("ripper.subtitles.engine")

SUBTITLES_DIR = Path.home() / "Downloads" / "Subtitles"
OPENS_BASE_URL = "https://api.opensubtitles.com/api/v1"
SUBDL_BASE_URL = "https://api.subdl.com/api/v1/subtitles"


def normalize_subtitle_encoding(file_path: Path) -> bool:
    """
    Detects encoding and converts subtitle file content to standard UTF-8 without BOM.
    Ensures media players (MPV, VLC, PotPlayer) render text cleanly without gibberish.
    """
    if not file_path.exists():
        return False

    raw_bytes = file_path.read_bytes()
    if not raw_bytes:
        return False

    # Try standard UTF-8 first
    try:
        decoded = raw_bytes.decode("utf-8-sig")
        if decoded.startswith("\ufeff"):
            decoded = decoded.lstrip("\ufeff")
        file_path.write_bytes(decoded.encode("utf-8"))
        return True
    except UnicodeDecodeError:
        pass

    # Try common encodings: Windows-1252, ISO-8859-1, UTF-16
    for enc in ["cp1252", "iso-8859-1", "utf-16", "gbk", "shift_jis"]:
        try:
            decoded = raw_bytes.decode(enc)
            file_path.write_text(decoded, encoding="utf-8")
            logger.info(f"[SubtitleEngine] Normalized subtitle {file_path.name} from {enc} to UTF-8")
            return True
        except UnicodeDecodeError:
            continue

    return False


class SubtitleEngine:
    """Unified subtitle acquisition engine supporting local cache, OpenSubtitles, and SubDL."""

    def __init__(self, download_dir: Optional[Path] = None, timeout: float = 6.0):
        self.download_dir = download_dir or SUBTITLES_DIR.expanduser()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def find_local_subtitle(self, title: str) -> Optional[Path]:
        """Scans local download folders for matching subtitle files."""
        clean_q = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        keywords = [w for w in clean_q.split() if len(w) > 2]
        if not keywords:
            return None

        dirs_to_check = [self.download_dir, Path.cwd()]
        for d in dirs_to_check:
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in (".srt", ".ass", ".vtt"):
                    fname = f.stem.lower()
                    if any(w in fname for w in keywords):
                        return f
        return None

    async def search_opensubtitles(
        self,
        title: str,
        year: Optional[str] = None,
        languages: str = "en,hi",
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[Dict[str, Any]]:
        """Queries OpenSubtitles REST v1."""
        key = api_key or get_config_value("opensubtitles_api_key", "")
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, verify=False)
            should_close = True

        results = []
        try:
            params = {"query": title, "languages": languages}
            if year:
                params["year"] = year

            headers = {"User-Agent": "RipperMediaEngine/1.0", "Accept": "application/json"}
            if key:
                headers["Api-Key"] = key

            resp = await client.get(f"{OPENS_BASE_URL}/subtitles", params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    attr = item.get("attributes", {})
                    files = attr.get("files", [])
                    file_id = files[0].get("file_id") if files else None
                    fname = files[0].get("file_name") if files else attr.get("release")

                    results.append({
                        "provider": "OpenSubtitles",
                        "subtitle_id": str(file_id) if file_id else "",
                        "file_name": fname or f"{title}.srt",
                        "language": attr.get("language", "en"),
                        "download_url": attr.get("url"),
                    })
        except Exception as e:
            logger.debug(f"[SubtitleEngine] OpenSubtitles query error: {e}")
        finally:
            if should_close:
                await client.aclose()

        return results

    async def search_subdl(
        self,
        title: str,
        languages: str = "EN,HI",
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[Dict[str, Any]]:
        """Queries SubDL API for movie subtitles."""
        key = api_key or get_config_value("subdl_api_key", "")
        if not key:
            return []

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, verify=False)
            should_close = True

        results = []
        try:
            params = {
                "api_key": key,
                "film_name": title,
                "languages": languages,
            }
            resp = await client.get(SUBDL_BASE_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                for sub in data.get("subtitles", []):
                    results.append({
                        "provider": "SubDL",
                        "subtitle_id": str(sub.get("sd_id", "")),
                        "file_name": sub.get("release_name") or f"{title}.srt",
                        "language": sub.get("language", "en"),
                        "download_url": sub.get("url"),
                    })
        except Exception as e:
            logger.debug(f"[SubtitleEngine] SubDL query error: {e}")
        finally:
            if should_close:
                await client.aclose()

        return results

    async def download_subtitle(
        self,
        item: Dict[str, Any],
        output_name: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[Path]:
        """Downloads subtitle content and normalizes file charset."""
        dest = self.download_dir / output_name
        dl_url = item.get("download_url")
        sub_id = item.get("subtitle_id")

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout, verify=False, follow_redirects=True)
            should_close = True

        try:
            content = None
            if dl_url and dl_url.startswith("http"):
                resp = await client.get(dl_url)
                if resp.status_code == 200:
                    content = resp.content
            elif sub_id and item.get("provider") == "OpenSubtitles":
                key = get_config_value("opensubtitles_api_key", "")
                hdrs = {"Api-Key": key} if key else {}
                resp = await client.post(
                    f"{OPENS_BASE_URL}/download",
                    json={"file_id": int(sub_id)},
                    headers=hdrs,
                )
                if resp.status_code == 200:
                    link = resp.json().get("link")
                    if link:
                        f_resp = await client.get(link)
                        if f_resp.status_code == 200:
                            content = f_resp.content

            if content and len(content) > 10:
                dest.write_bytes(content)
                normalize_subtitle_encoding(dest)
                return dest
        except Exception as e:
            logger.debug(f"[SubtitleEngine] Failed downloading subtitle: {e}")
        finally:
            if should_close:
                await client.aclose()

        return None

    async def fetch_best_subtitle(
        self,
        title: str,
        year: Optional[str] = None,
        language: str = "en",
    ) -> Optional[Path]:
        """
        End-to-end convenience method:
        Checks local disk -> searches OpenSubtitles -> searches SubDL -> downloads & normalizes.
        """
        local = self.find_local_subtitle(title)
        if local:
            normalize_subtitle_encoding(local)
            return local

        async with httpx.AsyncClient(timeout=self.timeout, verify=False, follow_redirects=True) as client:
            # 1. Try OpenSubtitles
            subs = await self.search_opensubtitles(title, year=year, languages=language, client=client)
            if subs:
                safe_name = f"{re.sub(r'[^a-zA-Z0-9]', '_', title)}_{language}.srt"
                dest = await self.download_subtitle(subs[0], safe_name, client=client)
                if dest:
                    return dest

            # 2. Try SubDL
            subs_subdl = await self.search_subdl(title, languages=language.upper(), client=client)
            if subs_subdl:
                safe_name = f"{re.sub(r'[^a-zA-Z0-9]', '_', title)}_{language}.srt"
                dest = await self.download_subtitle(subs_subdl[0], safe_name, client=client)
                if dest:
                    return dest

        return None
