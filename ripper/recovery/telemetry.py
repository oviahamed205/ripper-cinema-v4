"""
Structured Silent Self-Diagnostic Telemetry Engine (Commandment 10).
Writes clean, structured logs to ~/.ripper/engine.log without leaking stacktraces.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

LOG_DIR = Path.home() / ".ripper"
LOG_FILE = LOG_DIR / "engine.log"
LEGACY_LOG_DIR = Path.home() / ".unshorten"
LEGACY_LOG_FILE = LEGACY_LOG_DIR / "engine.log"


def log_event(category: str, message: str, details: Optional[Dict[str, Any]] = None, level: str = "INFO"):
    """Silently records an event to the local engine log file (and legacy .unshorten path for compatibility)."""
    try:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level.upper(),
            "category": category,
            "message": message,
            "details": details or {},
        }
        serialized = json.dumps(entry) + "\n"
        for target_dir, target_file in ((LOG_DIR, LOG_FILE), (LEGACY_LOG_DIR, LEGACY_LOG_FILE)):
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                with open(target_file, "a", encoding="utf-8") as f:
                    f.write(serialized)
            except Exception:
                pass
    except Exception:
        pass

