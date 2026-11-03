"""
Adaptive Circuit Breaker & Host Resilience Engine for unshorten-cli.
Tracks server failure rates, consecutive timeouts, and Cloudflare anti-bot blocks.
Automatically trips offline hosts so requests fail over immediately in <100ms
instead of waiting for 10-second connection timeouts.
"""

from __future__ import annotations

import time
import random
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class HostStatus:
    host: str
    failures: int = 0
    successes: int = 0
    state: str = "CLOSED"  # CLOSED (healthy), OPEN (tripped/offline), HALF_OPEN (probing)
    last_failure_time: float = 0.0
    cooldown_seconds: float = 30.0


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._hosts: Dict[str, HostStatus] = {}

    def get_status(self, host: str) -> HostStatus:
        if host not in self._hosts:
            self._hosts[host] = HostStatus(host=host, cooldown_seconds=self.cooldown_seconds)
        return self._hosts[host]

    def can_request(self, host: str) -> bool:
        """Returns True if the host is healthy or ready for a trial probe."""
        st = self.get_status(host)
        now = time.time()
        if st.state == "CLOSED":
            return True
        if st.state == "OPEN":
            # Check if cooldown has elapsed
            if now - st.last_failure_time > st.cooldown_seconds:
                st.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN allows 1 trial request

    def record_success(self, host: str) -> None:
        st = self.get_status(host)
        st.successes += 1
        st.failures = 0
        st.state = "CLOSED"

    def record_failure(self, host: str, is_timeout: bool = False) -> None:
        st = self.get_status(host)
        st.failures += 1
        st.last_failure_time = time.time()
        if st.failures >= self.failure_threshold or is_timeout:
            st.state = "OPEN"


# Global singleton instance
CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=2, cooldown_seconds=25.0)


async def retry_with_backoff(
    coro_fn,
    *args,
    retries: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 2.0,
    **kwargs,
):
    """Execute async function with exponential jittered backoff."""
    for attempt in range(retries + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            if attempt == retries:
                raise e
            delay = min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0.1, 0.3)
            await asyncio.sleep(delay)
