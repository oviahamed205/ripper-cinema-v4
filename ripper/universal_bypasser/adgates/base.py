"""
Base Ad-Gate Solver Interface.
Provides common HTTP session management, token parsing, and retry handling.
"""

from __future__ import annotations

import abc
import time
from typing import Dict, Optional

import httpx

from ripper.universal_bypasser.models import BypassContext, GateType, ShortlinkResult


class BaseAdGateSolver(abc.ABC):
    """Abstract base class for all Ad-Gate solvers."""

    name: str = "base_adgate"

    def __init__(self, context: Optional[BypassContext] = None):
        self.context = context or BypassContext()

    def get_client(self, follow_redirects: bool = True) -> httpx.AsyncClient:
        headers = {
            "User-Agent": self.context.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        headers.update(self.context.headers)
        return httpx.AsyncClient(
            headers=headers,
            timeout=self.context.timeout,
            follow_redirects=follow_redirects,
            verify=False,
            proxy=self.context.proxy
        )

    @abc.abstractmethod
    async def solve(self, url: str) -> ShortlinkResult:
        """Solves the target ad-gate URL and returns the final destination URL."""
        pass
