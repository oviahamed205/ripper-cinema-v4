"""
ripper.hoster_watchdog.registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In-memory and persistent domain alias & mirror registry.
Provides thread-safe URL domain remapping to ensure dead or blocked domains
are automatically redirected to active, live mirrors.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ripper.hoster_watchdog.registry")

REGISTRY_PATH = Path(__file__).parent / "domain_registry.json"


@dataclass
class ProviderRecord:
    name: str
    primary: str
    mirrors: List[str]
    active_mirror: str
    status: str = "online"  # "online", "degraded", "offline"
    latency_ms: float = 0.0


class DomainRegistry:
    """Manages provider mirror groups and transparently remaps hoster URLs."""

    def __init__(self, registry_file: Optional[Path] = None):
        self.file_path = registry_file or REGISTRY_PATH
        self.providers: Dict[str, ProviderRecord] = {}
        self.domain_to_provider: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        """Loads domain definitions from disk."""
        if not self.file_path.exists():
            return

        try:
            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            providers_raw = data.get("providers", {})
            self.providers.clear()
            self.domain_to_provider.clear()

            for key, info in providers_raw.items():
                record = ProviderRecord(
                    name=info.get("name", key),
                    primary=info.get("primary", ""),
                    mirrors=info.get("mirrors", []),
                    active_mirror=info.get("active_mirror", info.get("primary", "")),
                    status=info.get("status", "online"),
                    latency_ms=info.get("latency_ms", 0.0),
                )
                self.providers[key] = record

                # Map all mirror hostnames back to provider key
                for mirror_url in record.mirrors:
                    parsed = urllib.parse.urlparse(mirror_url)
                    host = parsed.netloc.lower()
                    if host:
                        self.domain_to_provider[host] = key
        except Exception as e:
            logger.error(f"[DomainRegistry] Failed to load registry: {e}")

    def save(self) -> None:
        """Saves current state to disk."""
        try:
            payload = {
                "version": "1.0.0",
                "providers": {
                    k: {
                        "name": v.name,
                        "primary": v.primary,
                        "mirrors": v.mirrors,
                        "active_mirror": v.active_mirror,
                        "status": v.status,
                        "latency_ms": v.latency_ms,
                    }
                    for k, v in self.providers.items()
                },
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"[DomainRegistry] Failed to save registry: {e}")

    def remap_url(self, url: str) -> str:
        """
        Rewrites a URL if its host belongs to a known provider whose active mirror differs.
        Preserves path, query parameters, and fragments.
        """
        if not url:
            return url

        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()

        provider_key = self.domain_to_provider.get(host)
        if not provider_key or provider_key not in self.providers:
            return url

        provider = self.providers[provider_key]
        if not provider.active_mirror:
            return url

        active_parsed = urllib.parse.urlparse(provider.active_mirror)
        if active_parsed.netloc.lower() == host:
            return url

        # Swap scheme and netloc with active mirror
        remapped = parsed._replace(scheme=active_parsed.scheme, netloc=active_parsed.netloc)
        return urllib.parse.urlunparse(remapped)

    def set_active_mirror(self, provider_key: str, mirror_url: str, latency_ms: float = 0.0) -> bool:
        """Updates the active mirror for a provider."""
        if provider_key not in self.providers:
            return False

        prov = self.providers[provider_key]
        prov.active_mirror = mirror_url
        prov.status = "online"
        prov.latency_ms = latency_ms

        if mirror_url not in prov.mirrors:
            prov.mirrors.append(mirror_url)
            parsed = urllib.parse.urlparse(mirror_url)
            if parsed.netloc:
                self.domain_to_provider[parsed.netloc.lower()] = provider_key

        self.save()
        logger.info(f"[DomainRegistry] Promoted active mirror for {provider_key}: {mirror_url} ({latency_ms:.1f}ms)")
        return True


# Global Singleton Instance
_global_registry: Optional[DomainRegistry] = None


def get_registry() -> DomainRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = DomainRegistry()
    return _global_registry
