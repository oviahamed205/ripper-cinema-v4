"""
Universal Bypasser Models & Type Definitions.
Defines strongly-typed dataclasses for shortlink results, container unrolling,
ad-gate categories, and bypass execution contexts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class GateType(str, Enum):
    """Categorization of shortlink, locker, or container target."""
    SIMPLE_REDIRECT = "simple_redirect"      # URL param or HTTP 30x direct redirect
    AD_GATE = "ad_gate"                      # Countdown, multi-step CSRF token post
    CONTAINER = "container"                  # Folder/locker containing multiple links (Filecrypt, Keeplinks)
    CLICK_N_LOAD = "click_n_load"            # Port 9666 CNL2 encrypted payload
    CLOUD_GATE = "cloud_gate"                # Turnstile/reCAPTCHA locked (Linkvertise, Lootlabs)
    DIRECT_HOSTER = "direct_hoster"          # Already a direct hoster URL (Streamtape, etc.)
    UNKNOWN = "unknown"


@dataclass
class ShortlinkResult:
    """Result of resolving a single shortlink or ad-gate URL."""
    original_url: str
    resolved_url: Optional[str] = None
    gate_type: GateType = GateType.UNKNOWN
    success: bool = False
    duration: float = 0.0
    solver_used: Optional[str] = None
    intermediate_urls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_url": self.original_url,
            "resolved_url": self.resolved_url,
            "gate_type": self.gate_type.value,
            "success": self.success,
            "duration": self.duration,
            "solver_used": self.solver_used,
            "intermediate_urls": self.intermediate_urls,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class ContainerResult:
    """Result of unrolling a container, folder, or encrypted link locker."""
    container_url: str
    title: Optional[str] = None
    gate_type: GateType = GateType.CONTAINER
    unlocked_urls: List[str] = field(default_factory=list)
    total_links: int = 0
    success: bool = False
    duration: float = 0.0
    solver_used: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.unlocked_urls and not self.total_links:
            self.total_links = len(self.unlocked_urls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_url": self.container_url,
            "title": self.title,
            "gate_type": self.gate_type.value,
            "unlocked_urls": self.unlocked_urls,
            "total_links": self.total_links,
            "success": self.success,
            "duration": self.duration,
            "solver_used": self.solver_used,
            "error": self.error,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class CNLPayload:
    """Encrypted Click'n'Load payload received from web page."""
    crypted: str
    jk: str
    source: Optional[str] = None
    passwords: Optional[str] = None
    package_name: Optional[str] = None


@dataclass
class BypassContext:
    """Context passed across bypass pipelines, including cookies, headers, and proxies."""
    timeout: float = 20.0
    max_retries: int = 3
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    proxy: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    use_cloud_bridge: bool = True
    use_playwright_fallback: bool = True
    firecrawl_api_key: Optional[str] = None
