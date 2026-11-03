"""
Watchlist & Favorites Manager for unshorten-cli.
Stores movies/shows saved to watch later at ~/.ripper/watchlist.json.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from .config import CONFIG_DIR

WATCHLIST_FILE = CONFIG_DIR / "watchlist.json"


def load_watchlist() -> List[Dict[str, Any]]:
    """Load watchlist from disk."""
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_watchlist(items: List[Dict[str, Any]]) -> bool:
    """Save watchlist to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as ffile:
            json.dump(items, ffile, indent=2)
        return True
    except Exception:
        return False


def add_to_watchlist(
    title: str,
    url: str,
    site_name: str = "",
    year: Optional[str] = None,
    quality: Optional[str] = None,
    poster_url: Optional[str] = None,
) -> bool:
    """Add a movie or series to local watchlist."""
    items = load_watchlist()
    # Avoid duplicates by URL or title
    for it in items:
        if it.get("url") == url or it.get("title").lower() == title.lower():
            return True

    new_entry = {
        "title": title,
        "url": url,
        "site_name": site_name,
        "year": year,
        "quality": quality,
        "poster_url": poster_url,
        "added_at": time.strftime("%Y-%m-%d %H:MM:%S"),
    }
    items.insert(0, new_entry)
    return save_watchlist(items)


def remove_from_watchlist(title_or_url: str) -> bool:
    """Remove a movie from watchlist by title or URL."""
    items = load_watchlist()
    orig_len = len(items)
    items = [i for i in items if i.get("title") != title_or_url and i.get("url") != title_or_url]
    if len(items) != orig_len:
        return save_watchlist(items)
    return False


def get_watchlist() -> List[Dict[str, Any]]:
    """Return current watchlist."""
    return load_watchlist()

