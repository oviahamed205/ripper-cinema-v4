"""
Persistent CookieJar for Ripper Anti-Bot Bypass.
Persists clearance cookies (cf_clearance, __cf_bm, session tokens) to ~/.ripper/cookies.json
so expensive browser solves only happen once per domain.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional


COOKIES_PATH = Path.home() / ".ripper" / "cookies.json"


class ClearanceCookieJar:
    """Manages persistent clearance and session cookies across scans and restarts."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or COOKIES_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._store: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._store = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._store = {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._store, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_cookies_for_domain(self, domain: str) -> Dict[str, str]:
        """Return non-expired cookies for a specific domain."""
        now = time.time()
        dom = domain.lower().strip(".")
        result: Dict[str, str] = {}
        for stored_dom, entry in list(self._store.items()):
            if dom.endswith(stored_dom) or stored_dom.endswith(dom):
                if entry.get("expires_at", 0) > now:
                    result.update(entry.get("cookies", {}))
                else:
                    # Purge expired
                    self._store.pop(stored_dom, None)
        return result

    def set_cookies_for_domain(self, domain: str, cookies: Dict[str, str], ttl_seconds: float = 7200.0) -> None:
        """Store cookies for a domain with TTL (default 2 hours)."""
        dom = domain.lower().strip(".")
        self._store[dom] = {
            "cookies": cookies,
            "expires_at": time.time() + ttl_seconds,
            "stored_at": time.time(),
        }
        self._save()

    def clear(self) -> None:
        """Clear all stored cookies."""
        self._store = {}
        self._save()


# Global cookie jar instance
GLOBAL_COOKIE_JAR = ClearanceCookieJar()