"""
Unit Tests for Phase 2: Autonomous Self-Healing & Recovery Engine
"""

import pytest
import asyncio
from pathlib import Path
from ripper.recovery import (
    log_event,
    JitterShield,
    RecoveryManager,
    resolve_with_doh_fallback,
)
from ripper.resilience import CircuitBreaker


def test_silent_telemetry():
    log_event("TEST_CATEGORY", "Test message from unit test", {"key": "val"}, level="INFO")
    log_path = Path.home() / ".unshorten" / "engine.log"
    assert log_path.exists()
    assert log_path.stat().st_size > 0


@pytest.mark.anyio
async def test_jitter_shield():
    import time
    shield = JitterShield(min_jitter_ms=5, max_jitter_ms=15)
    t0 = time.monotonic()
    await shield.throttle("example.com")
    await shield.throttle("example.com")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.004


def test_recovery_manager_circuit():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    rec = RecoveryManager(cb)
    host = "failing-mirror.net"

    assert rec.should_skip_host(host) is False

    rec.record_host_failure(host)
    assert rec.should_skip_host(host) is False

    # Second failure -> Trips circuit
    rec.record_host_failure(host)
    assert rec.should_skip_host(host) is True

    # Record success -> Resets
    rec.record_host_success(host)
    assert rec.should_skip_host(host) is False


@pytest.mark.anyio
async def test_doh_guard_resolution():
    ip = await resolve_with_doh_fallback("cloudflare.com")
    assert ip is not None
    assert len(ip.split(".")) == 4
