"""
Circuit breaker and domain health guard for Ripper Resolver.
Fast-fails requests to dead, broken, or rate-limited hosts to avoid latency bottlenecks.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from ...cache import GLOBAL_CACHE


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


CIRCUIT_FAIL_THRESHOLD = max(1, _env_int("UNSHORTEN_CIRCUIT_FAIL_THRESHOLD", 3))
CIRCUIT_TTL = _env_float("UNSHORTEN_CIRCUIT_TTL", 300.0)


async def is_circuit_open(domain: str) -> bool:
    """Check if circuit breaker is active for domain due to recent repeated failures."""
    if not domain:
        return False
    clean_domain = str(domain).strip().lower()
    try:
        if GLOBAL_CACHE:
            status = await GLOBAL_CACHE.get("circuit", clean_domain)
            return status == "OPEN"
        return False
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


async def record_domain_failure(domain: str, status_code: int = 0) -> None:
    """Increment domain failure counter and open circuit if threshold exceeded."""
    if not domain:
        return
    clean_domain = str(domain).strip().lower()
    try:
        if not GLOBAL_CACHE:
            return
        key = f"fail_cnt_{clean_domain}"
        raw = await GLOBAL_CACHE.get("circuit", key)
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            count = 0
        count += 1
        await GLOBAL_CACHE.set("circuit", key, count, ttl=CIRCUIT_TTL)
        if count >= CIRCUIT_FAIL_THRESHOLD:
            await GLOBAL_CACHE.set("circuit", clean_domain, "OPEN", ttl=CIRCUIT_TTL)
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def record_domain_success(domain: str) -> None:
    """Reset domain failure counter on successful network request."""
    if not domain:
        return
    clean_domain = str(domain).strip().lower()
    try:
        if not GLOBAL_CACHE:
            return
        await GLOBAL_CACHE.invalidate("circuit", clean_domain)
        await GLOBAL_CACHE.invalidate("circuit", f"fail_cnt_{clean_domain}")
    except asyncio.CancelledError:
        raise
    except Exception:
        return