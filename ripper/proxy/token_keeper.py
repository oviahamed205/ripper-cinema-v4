"""
Ephemeral Token Keepalive Worker.
Refreshes stream tokens before the 10-minute expiry window kills playback mid-movie.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Dict, Optional


class TokenKeeper:
    """Tracks active streaming sessions and triggers token renewals."""

    def __init__(self, refresh_interval_seconds: float = 480.0) -> None:
        self.refresh_interval = refresh_interval_seconds
        self._tokens: Dict[str, Dict[str, Any]] = {}

    def register_session(self, session_id: str, refresh_callback: Optional[Callable] = None) -> None:
        self._tokens[session_id] = {
            "registered_at": time.time(),
            "last_refreshed": time.time(),
            "callback": refresh_callback,
        }

    def touch(self, session_id: str) -> None:
        """Mark session as actively being watched."""
        if session_id in self._tokens:
            self._tokens[session_id]["last_refreshed"] = time.time()

    def remove(self, session_id: str) -> None:
        self._tokens.pop(session_id, None)


GLOBAL_TOKEN_KEEPER = TokenKeeper()