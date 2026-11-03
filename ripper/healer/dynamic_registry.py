"""
ripper.healer.dynamic_registry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Persistent self-learning memory and dynamic rule cache.
Stores healed domain aliases, custom CSS/XPath selectors, honeypot blacklists,
and promotes winning extraction strategies to the front of the queue.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .models import HealingStrategy

logger = logging.getLogger("ripper.healer.dynamic_registry")

DEFAULT_SCHEMA: Dict[str, Any] = {
    "version": "2.1.0",
    "domain_aliases": {},
    "promoted_strategies": {},
    "custom_selectors": {},
    "blacklist_urls": [
        "vglist.cv",
        "vegamovies-apk.com",
        "adsterra.com",
        "bestdealfor.life",
        "apk-download",
    ],
    "metrics": {
        "total_heal_events": 0,
        "successful_heals": 0,
        "strategy_counts": {},
        "last_healed_at": None,
    },
}


class DynamicRegistry:
    """
    Thread-safe, atomic persistent storage for self-healed extraction rules.
    """

    def __init__(self, registry_file_path: Optional[str] = None):
        if not registry_file_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            registry_file_path = os.path.join(data_dir, "healer_registry.json")

        self.file_path = registry_file_path
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        """Loads registry JSON from disk, initializing defaults if absent or corrupted."""
        if not os.path.exists(self.file_path):
            self._atomic_save(DEFAULT_SCHEMA)
            return dict(DEFAULT_SCHEMA)

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all root keys exist
                for k, v in DEFAULT_SCHEMA.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            logger.warning(f"[Registry] Corrupted registry file ({e}); recreating default.")
            self._atomic_save(DEFAULT_SCHEMA)
            return dict(DEFAULT_SCHEMA)

    def _atomic_save(self, data: Dict[str, Any]) -> None:
        """Writes data to a temporary file in the same directory, then atomically replaces it."""
        dirname = os.path.dirname(self.file_path)
        os.makedirs(dirname, exist_ok=True)

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False, encoding="utf-8") as tf:
                temp_file = tf.name
                json.dump(data, tf, indent=2, ensure_ascii=False)

            os.replace(temp_file, self.file_path)
        except Exception as e:
            logger.error(f"[Registry] Atomic save failed: {e}")
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def save(self) -> None:
        """Persists in-memory registry to disk."""
        self._atomic_save(self._data)

    def extract_domain(self, url_or_domain: str) -> str:
        """Normalizes a URL or hostname string into a base domain key."""
        if "://" in url_or_domain:
            parsed = urlparse(url_or_domain)
            return parsed.netloc.lower()
        return url_or_domain.lower().strip()

    # -------------------------------------------------------------------------
    # Domain Aliasing & Mirror Routing
    # -------------------------------------------------------------------------

    def get_domain_alias(self, domain_or_url: str) -> str:
        """Returns the canonical active mirror if an alias exists, else the input domain."""
        domain = self.extract_domain(domain_or_url)
        aliases = self._data.get("domain_aliases", {})
        return aliases.get(domain, domain)

    def map_domain_alias(self, old_domain: str, active_domain: str) -> None:
        """Registers a domain migration / mirror reroute."""
        old = self.extract_domain(old_domain)
        active = self.extract_domain(active_domain)
        if old == active:
            return

        aliases = self._data.setdefault("domain_aliases", {})
        aliases[old] = active
        logger.info(f"[Registry] Learned domain alias: {old} -> {active}")
        self.save()

    # -------------------------------------------------------------------------
    # Strategy Promotion Memory
    # -------------------------------------------------------------------------

    def get_promoted_strategies(self, domain_or_url: str) -> List[HealingStrategy]:
        """Returns ordered list of previously successful strategies for this domain."""
        domain = self.extract_domain(domain_or_url)
        # Check canonical domain
        canonical = self.get_domain_alias(domain)
        promotions = self._data.get("promoted_strategies", {})

        strat_strings = promotions.get(canonical, [])
        result = []
        for s in strat_strings:
            try:
                result.append(HealingStrategy(s))
            except ValueError:
                pass
        return result

    def record_success(
        self,
        domain_or_url: str,
        strategy: HealingStrategy,
        latency_ms: float = 0.0,
    ) -> None:
        """
        Records a successful extraction and promotes the winning strategy
        to the top priority for subsequent crawls.
        """
        domain = self.extract_domain(domain_or_url)
        canonical = self.get_domain_alias(domain)

        promotions = self._data.setdefault("promoted_strategies", {})
        current_list = promotions.get(canonical, [])

        strat_val = strategy.value
        # Reorder list: promote strategy to front
        if strat_val in current_list:
            current_list.remove(strat_val)
        current_list.insert(0, strat_val)
        promotions[canonical] = current_list

        # Update metrics
        metrics = self._data.setdefault("metrics", {})
        metrics["total_heal_events"] = metrics.get("total_heal_events", 0) + 1
        metrics["successful_heals"] = metrics.get("successful_heals", 0) + 1
        metrics["last_healed_at"] = time.time()

        strategy_counts = metrics.setdefault("strategy_counts", {})
        strategy_counts[strat_val] = strategy_counts.get(strat_val, 0) + 1

        logger.debug(f"[Registry] Promoted {strat_val} to priority 1 for {canonical} (took {latency_ms:.1f}ms)")
        self.save()

    # -------------------------------------------------------------------------
    # Custom Selector Storage
    # -------------------------------------------------------------------------

    def get_custom_selectors(self, domain_or_url: str) -> Dict[str, Any]:
        """Returns cached CSS/XPath selectors discovered for this domain."""
        domain = self.get_domain_alias(self.extract_domain(domain_or_url))
        selectors = self._data.get("custom_selectors", {})
        return selectors.get(domain, {})

    def set_custom_selector(self, domain_or_url: str, key: str, selector: str) -> None:
        """Saves a discovered CSS/XPath selector for future heuristic fast-pathing."""
        domain = self.get_domain_alias(self.extract_domain(domain_or_url))
        selectors = self._data.setdefault("custom_selectors", {})
        domain_sels = selectors.setdefault(domain, {})
        domain_sels[key] = selector
        self.save()

    # -------------------------------------------------------------------------
    # Honeypot Blacklist Management
    # -------------------------------------------------------------------------

    def is_blacklisted(self, url: str) -> bool:
        """Checks if a URL contains any blacklisted patterns or domains."""
        url_lower = url.lower()
        blacklist = self._data.get("blacklist_urls", [])
        return any(pattern.lower() in url_lower for pattern in blacklist)

    def add_to_blacklist(self, pattern: str) -> None:
        """Adds a newly discovered ad-trap pattern to persistent blacklist."""
        clean = pattern.lower().strip()
        blacklist = self._data.setdefault("blacklist_urls", [])
        if clean not in blacklist:
            blacklist.append(clean)
            logger.info(f"[Registry] Blacklisted new honeypot pattern: {clean}")
            self.save()
