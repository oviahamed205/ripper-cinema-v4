"""
unshorten-cli: Universal Link Unshortener & Safe Redirect Resolver
"""

__version__ = "1.0.0"

_IMPORT_ERRORS = []

# Activate Autonomous AI Self-Healing & Problem Resolution Watchdog
try:
    from .ai_engine import activate_ai_self_healing
    activate_ai_self_healing()
    from .healer_engine import get_global_watchdog
    get_global_watchdog().install()
except Exception:
    pass

try:
    from .models import HopInfo, UnshortenResult, SafetyReport, ServerMirror
except Exception as _e:
    _IMPORT_ERRORS.append(f"models: {_e}")

try:
    from .resolver import unshorten_url, unshorten_url_sync
except Exception as _e:
    _IMPORT_ERRORS.append(f"resolver: {_e}")

try:
    from .safety import analyze_destination_safety
except Exception as _e:
    _IMPORT_ERRORS.append(f"safety: {_e}")

try:
    from .batch import batch_unshorten_urls
except Exception as _e:
    _IMPORT_ERRORS.append(f"batch: {_e}")

__all__ = [
    "HopInfo",
    "UnshortenResult",
    "SafetyReport",
    "ServerMirror",
    "unshorten_url",
    "unshorten_url_sync",
    "analyze_destination_safety",
    "batch_unshorten_urls",
    "_IMPORT_ERRORS",
]
