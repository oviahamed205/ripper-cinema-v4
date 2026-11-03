"""
Base Container Unroller Interface.
Unrolls folders, link lockers, and multi-link containers into lists of direct hoster URLs.
"""

from __future__ import annotations

import abc
from typing import Optional

import httpx

from ripper.universal_bypasser.models import BypassContext, ContainerResult


class BaseContainerUnroller(abc.ABC):
    """Abstract base class for container and link locker unrollers."""

    name: str = "base_container"

    def __init__(self, context: Optional[BypassContext] = None):
        self.context = context or BypassContext()

    def get_client(self, follow_redirects: bool = True) -> httpx.AsyncClient:
        headers = {
            "User-Agent": self.context.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
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
    async def unroll(self, url: str) -> ContainerResult:
        """Crawls and unpacks all individual hoster links from the container."""
        pass
