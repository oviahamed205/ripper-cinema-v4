"""
ripper.stremio_addons
~~~~~~~~~~~~~~~~~~~~~

Stremio HTTP Addon Protocol Client & Catalog Aggregator.
Reverse-engineered from Stremio v3 Addon Specification and MovieBox-Tui addons:
- Normalizes stremio:// protocol URLs and HTTP endpoints to /manifest.json
- Validates addon manifests, supported resource types (stream, catalog, meta)
- Resolves streams for movies (tt...) and series (tt...:season:episode)
- Integrates community addons (Torrentio, CyberFlix, Cinemeta, OpenSubtitles).
"""

from __future__ import annotations

import re
import urllib.parse
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import httpx


@dataclass
class StremioStream:
    name: str
    title: str
    url: Optional[str] = None
    info_hash: Optional[str] = None
    file_idx: Optional[int] = None
    quality: Optional[str] = None
    behavior_hints: Dict[str, Any] = field(default_factory=dict)
    addon_name: str = "Stremio Addon"


@dataclass
class AddonManifest:
    id: str
    name: str
    version: str
    description: str
    resources: List[str]
    types: List[str]
    base_url: str


class StremioAddonClient:
    """Client for communicating with standard Stremio v3 HTTP addons."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    @staticmethod
    def normalize_manifest_url(raw: str) -> str:
        """Normalize stremio:// or raw URLs to https://.../manifest.json."""
        url = raw.strip()
        if url.startswith("stremio://"):
            url = "https://" + url[len("stremio://") :]
        elif not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        if not url.endswith("/manifest.json") and "/manifest.json?" not in url:
            if url.endswith("/"):
                url += "manifest.json"
            else:
                url += "/manifest.json"
        return url

    @staticmethod
    def get_base_addon_url(manifest_url: str) -> str:
        """Extract root service base URL from manifest URL."""
        norm = StremioAddonClient.normalize_manifest_url(manifest_url)
        idx = norm.rfind("/manifest.json")
        if idx != -1:
            return norm[:idx]
        return norm.rstrip("/")

    async def _fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch JSON using httpx with automatic curl_cffi Chrome TLS fallback on 403/503."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass

        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(url, impersonate="chrome120", timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        return None

    async def fetch_manifest(self, manifest_url: str) -> Optional[AddonManifest]:
        """Fetch and validate remote addon manifest.json."""
        target = self.normalize_manifest_url(manifest_url)
        data = await self._fetch_json(target)
        if not data or not isinstance(data, dict):
            return None

        resources_raw = data.get("resources", [])
        resources: List[str] = []
        for r in resources_raw:
            if isinstance(r, str):
                resources.append(r)
            elif isinstance(r, dict) and "name" in r:
                resources.append(r["name"])

        return AddonManifest(
            id=data.get("id", "addon.unknown"),
            name=data.get("name", "Unnamed Addon"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            resources=resources,
            types=data.get("types", ["movie", "series"]),
            base_url=self.get_base_addon_url(target),
        )

    async def get_streams(
        self,
        base_addon_url: str,
        media_type: str,
        imdb_id: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> List[StremioStream]:
        """
        Query addon stream endpoint: /stream/{type}/{id}.json.
        For series: id is formatted as {imdb_id}:{season}:{episode}.
        """
        streams: List[StremioStream] = []
        clean_type = "series" if (season is not None and episode is not None) else media_type
        target_id = f"{imdb_id}:{season}:{episode}" if (clean_type == "series" and season is not None) else imdb_id
        endpoint = f"{base_addon_url.rstrip('/')}/stream/{clean_type}/{target_id}.json"

        data = await self._fetch_json(endpoint)
        if not data or not isinstance(data, dict):
            return streams

        raw_streams = data.get("streams", [])
        for s in raw_streams:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "Stream")
            title = s.get("title") or s.get("description") or name
            url = s.get("url")
            info_hash = s.get("infoHash")
            file_idx = s.get("fileIdx")
            behavior = s.get("behaviorHints", {})

            # Extract quality from name or title
            quality = "1080p"
            q_match = re.search(r'\b(2160p|4K|1080p|720p|480p)\b', f"{name} {title}", re.I)
            if q_match:
                quality = q_match.group(1).lower()

            streams.append(
                StremioStream(
                    name=name,
                    title=title,
                    url=url,
                    info_hash=info_hash,
                    file_idx=file_idx,
                    quality=quality,
                    behavior_hints=behavior if isinstance(behavior, dict) else {},
                    addon_name=name,
                )
            )

        return streams
