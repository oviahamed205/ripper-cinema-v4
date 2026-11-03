"""
BaseHostDecoder interface & StreamInfo data contracts for Ripper AnyStream Suite.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StreamInfo:
    """Represents a resolved direct playable stream."""
    stream_url: str
    headers: Dict[str, str] = field(default_factory=dict)
    quality: str = "auto"
    format: str = "mp4"  # 'mp4', 'hls', 'dash'
    host_name: str = ""
    title: str = ""
    subtitles: List[Dict[str, str]] = field(default_factory=list)


class BaseHostDecoder(ABC):
    """Abstract base class for video host decoders."""

    name: str = "generic"
    priority: int = 50

    @abstractmethod
    def can_decode(self, url: str, html: Optional[str] = None) -> bool:
        """Return True if this decoder handles the target host."""
        pass

    @abstractmethod
    async def decode(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        """Decode video host into a direct StreamInfo."""
        pass