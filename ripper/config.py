"""
Configuration Management System for unshorten-cli.
Stores user preferences, TMDB API keys, and default flags at ~/.ripper/config.json.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

CONFIG_DIR = Path.home() / ".ripper"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "tmdb_api_key": "",
    "tmdb_read_access_token": "",
    "use_apis": True,
    "preferred_player": "potplayer",
    "default_timeout": 5.0,
    "max_hops": 15,
    "cache_ttl": 900,
    "preferred_quality": "1080p",
    "preferred_language": "hindi",
}


def load_config() -> Dict[str, Any]:
    """Load configuration from disk with default fallback."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception:
            pass
    else:
        # Seed initial config from ~/.ripper if available
        legacy_cfg = Path.home() / ".ripper" / "config.json"
        if legacy_cfg.exists():
            try:
                with open(legacy_cfg, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        cfg.update(saved)
                        save_config(cfg)
            except Exception:
                pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> bool:
    """Save configuration to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


def get_config_value(key: str, default: Any = None) -> Any:
    """Get single configuration parameter."""
    cfg = load_config()
    return cfg.get(key, default if default is not None else DEFAULT_CONFIG.get(key))


def set_config_value(key: str, value: Any) -> bool:
    """Set and persist a single configuration parameter."""
    cfg = load_config()
    cfg[key] = value
    return save_config(cfg)

