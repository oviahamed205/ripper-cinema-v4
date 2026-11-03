"""
Base Portal Resolver Abstract Class (Commandments 1, 2, 3).
Provides safe tree traversal, error triage, and common HTTP hooks.
"""

from __future__ import annotations

import re
import httpx
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PortalStreamResult:
    direct_url: str
    filename: Optional[str] = None
    filesize_bytes: Optional[int] = None
    resolution: Optional[str] = None
    portal_name: str = "Unknown"
    is_hls: bool = False


@dataclass
class SearchResult:
    portal_id: str
    title: str
    url: str
    year: Optional[str] = None
    poster_url: Optional[str] = None
    rating: Optional[str] = None
    is_series: bool = False
    quality: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaStream:
    url: str
    quality: str = "1080p"
    format: str = "mp4"
    headers: Dict[str, str] = field(default_factory=dict)
    source: str = "Direct"
    bitrate: Optional[int] = None
    size_bytes: Optional[int] = None


class PortalCategory:
    HOLLYWOOD = "hollywood"
    BOLLYWOOD = "bollywood"
    ANIME = "anime"
    SERIES = "series"
    IPTV = "iptv"


def safe_get(d: Any, *keys: Any, default: Any = None) -> Any:
    """Safe recursive dictionary and list traverser (yt-dlp standard)."""
    current = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k)
        elif isinstance(current, (list, tuple)) and isinstance(k, int):
            if 0 <= k < len(current):
                current = current[k]
            else:
                return default
        else:
            return default
        if current is None:
            return default
    return current


class BasePortalResolver(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the portal."""
        pass

    @property
    @abstractmethod
    def supported_domains(self) -> List[str]:
        """List of domain strings matching this portal."""
        pass

    def can_handle(self, url: str) -> bool:
        """Determines whether this portal can handle the given URL."""
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
        return any(d in netloc for d in self.supported_domains)

    @abstractmethod
    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        """Asynchronously extracts direct stream URLs from the portal page."""
        pass


class MoviePortal(BasePortalResolver):
    """Extended base class for search-capable movie and TV portals."""

    def __init__(self, portal_id: str, name: str, base_url: str, categories: Optional[List[str]] = None):
        self._portal_id = portal_id
        self._name = name
        self.base_url = base_url
        self.categories = categories or []

    @property
    def portal_id(self) -> str:
        return self._portal_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_domains(self) -> List[str]:
        from urllib.parse import urlparse
        netloc = urlparse(self.base_url).netloc.lower()
        return [netloc] if netloc else []

    async def resolve(self, client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
        return []

