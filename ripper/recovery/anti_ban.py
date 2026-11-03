"""
Autonomous Anti-Ban & Jitter Shield (Commandment 7).
Token-bucket rate limiter with randomized micro-jitter (30ms–150ms).
"""

from __future__ import annotations

import anyio
import random
import time
from typing import Dict


class JitterShield:
    def __init__(self, min_jitter_ms: int = 30, max_jitter_ms: int = 150):
        self.min_jitter = min_jitter_ms / 1000.0
        self.max_jitter = max_jitter_ms / 1000.0
        self._last_call: Dict[str, float] = {}

    async def throttle(self, host: str):
        """Applies adaptive micro-jitter before making concurrent requests to the same host."""
        now = time.monotonic()
        last = self._last_call.get(host, 0.0)
        delay = random.uniform(self.min_jitter, self.max_jitter)
        elapsed = now - last

        if elapsed < delay:
            await anyio.sleep(delay - elapsed)

        self._last_call[host] = time.monotonic()


GLOBAL_SHIELD = JitterShield()
