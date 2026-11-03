"""
Autonomous Self-Healing & Error Triage Engine.
Provides silent telemetry, anti-ban rate limiting, DoH guards, and circuit breaking.
"""

from .telemetry import log_event
from .anti_ban import JitterShield, GLOBAL_SHIELD
from .doh_guard import resolve_with_doh_fallback
from .circuit_manager import RecoveryManager, GLOBAL_RECOVERY

__all__ = [
    "log_event",
    "JitterShield",
    "GLOBAL_SHIELD",
    "resolve_with_doh_fallback",
    "RecoveryManager",
    "GLOBAL_RECOVERY",
]
