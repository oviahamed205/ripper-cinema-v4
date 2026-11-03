"""
ripper.hoster_watchdog
~~~~~~~~~~~~~~~~~~~~~~

Top-level module for the Auto-Hoster Crawler & Provider Watchdog.
Exposes background scheduled polling, domain remapping, and health queries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .registry import DomainRegistry, get_registry
from .scanner import HosterScanner
from .dns_tracker import DoHTracker

logger = logging.getLogger("ripper.hoster_watchdog")

__all__ = [
    "DomainRegistry",
    "get_registry",
    "HosterScanner",
    "DoHTracker",
    "remap_hoster_url",
    "start_watchdog_background_task",
]


def remap_hoster_url(url: str) -> str:
    """Convenience helper to remap a URL to its active mirror."""
    return get_registry().remap_url(url)


async def start_watchdog_background_task(interval_seconds: float = 1800.0) -> None:
    """Runs periodic health scans in the background."""
    scanner = HosterScanner()
    while True:
        try:
            logger.info("[Watchdog] Starting periodic provider health scan...")
            await scanner.scan_all_providers()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Watchdog] Background scan error: {e}")

        await asyncio.sleep(interval_seconds)
