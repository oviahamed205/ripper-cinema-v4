"""
BaseResolverHandler interface & data contracts for Ripper Resolver Engine.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..models import HopInfo, UnshortenResult, ServerMirror


def make_hop(
    url: str,
    status_code: int = 200,
    redirect_type: str = "Direct",
    extra_details: str = "",
    hop_number: int = 0,
) -> HopInfo:
    """Helper to construct standard HopInfo instances across handlers."""
    return HopInfo(
        hop_number=hop_number,
        url=url,
        status_code=status_code,
        redirect_type=redirect_type,
        extra_details=extra_details,
    )


@dataclass
class ResolutionContext:
    """Carries execution state across recursive resolution hops."""
    depth: int = 0
    max_depth: int = 25
    hops: List[HopInfo] = field(default_factory=list)
    visited_urls: Set[str] = field(default_factory=set)
    extra_headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0
    impersonate_chrome: bool = True
    use_stealth_browser: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseResolverHandler(ABC):
    """Abstract interface that every site-specific resolver plugin must implement."""

    name: str = "base"
    priority: int = 50  # Lower number = higher priority

    @abstractmethod
    def can_handle(self, url: str, html: Optional[str] = None) -> bool:
        """Return True if this handler recognizes the URL or HTML signatures."""
        pass

    @abstractmethod
    async def resolve(
        self,
        url: str,
        client: Any,
        context: ResolutionContext,
    ) -> Optional[Tuple[str, List[HopInfo]]]:
        """
        Resolve the given URL by one or more steps.
        Returns:
            (next_or_final_url, list_of_hops_produced) or None if resolution failed.
        """
        pass

    def extract_mirrors(self, html: str, base_url: str) -> List[ServerMirror]:
        """Extract server mirror options (e.g. HubCloud, Pixeldrain, Cloudflare R2) if present."""
        return []