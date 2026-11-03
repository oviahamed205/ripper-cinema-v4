"""
Watch History & Streaming Analytics for unshorten-cli.
Stores all played streams and downloads in ~/.ripper/history.json.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from .config import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "history.json"


def load_history() -> List[Dict[str, Any]]:
    """Load playback history from disk."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_history(items: List[Dict[str, Any]]) -> bool:
    """Save playback history to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
        return True
    except Exception:
        return False


def add_to_history(
    title: str,
    url: str,
    quality: Optional[str] = None,
    site_name: Optional[str] = None,
    duration: Optional[str] = None,
    favorite: bool = False,
) -> bool:
    """Add an entry to playback history."""
    items = load_history()
    new_entry = {
        "title": title,
        "url": url,
        "quality": quality,
        "site_name": site_name,
        "duration": duration,
        "favorite": favorite,
        "played_at": time.strftime("%Y-%m-%d %H:M:%S"),
    }
    items.insert(0, new_entry)
    return save_history(items[:100])


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent playback history."""
    return load_history()[:limit]


def get_stats() -> Dict[str, Any]:
    """Compute playback analytics and statistics."""
    hist = load_history()
    total = len(hist)
    sites: Dict[str, int] = {}
    for h in hist:
        s = h.get("site_name") or "Unknown"
        sites[s] = sites.get(s, 0) + 1
    top_site = max(sites.items(), key=lambda x: x[1])[0] if sites else "None"

    return {
        "total_streams": total,
        "top_source_site": top_site,
        "sites_breakdown": sites,
    }

