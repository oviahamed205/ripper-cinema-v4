"""
Adaptive Circuit Breaker & Failover Manager (Commandment 6).
Protects against 10-second request hangs by failing over in <50ms.
"""

from __future__ import annotations

from ..resilience import CircuitBreaker, CIRCUIT_BREAKER
from .telemetry import log_event


class RecoveryManager:
    def __init__(self, breaker: CircuitBreaker = CIRCUIT_BREAKER):
        self.breaker = breaker

    def should_skip_host(self, host: str) -> bool:
        """Returns True if host is currently open/failing and should be skipped immediately."""
        can_req = self.breaker.can_request(host)
        if not can_req:
            log_event("CIRCUIT_TRIP", f"Host '{host}' is TRIPPED OPEN. Skipping in <1ms to next healthy mirror.")
        return not can_req

    def record_host_success(self, host: str):
        self.breaker.record_success(host)

    def record_host_failure(self, host: str):
        self.breaker.record_failure(host)
        log_event("CIRCUIT_FAILURE", f"Host '{host}' reported failure or timeout.")


GLOBAL_RECOVERY = RecoveryManager()
