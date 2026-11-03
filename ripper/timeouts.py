"""
Timeout cascade configuration and retry budget manager for unshorten-cli.
Prevents false timeouts on slow DNS / overloaded mirrors and recovers transient network drops.
"""

import asyncio
from dataclasses import dataclass
from typing import Callable, Any, Optional
import httpx


@dataclass
class TimeoutCascade:
    connect: float = 3.0
    read: float = 8.0
    write: float = 5.0
    pool: float = 2.0
    total: float = 12.0


def build_timeout(cascade: Optional[Any] = None, flat_total: Optional[float] = None) -> httpx.Timeout:
    """Build httpx.Timeout from TimeoutCascade, float seconds, or custom total."""
    if isinstance(cascade, (int, float)):
        flat_total = float(cascade)
        cascade = None

    if flat_total is not None and flat_total > 0:
        connect = min(3.0, flat_total * 0.3)
        read = max(2.0, flat_total * 0.7)
        return httpx.Timeout(timeout=flat_total, connect=connect, read=read, write=5.0, pool=2.0)

    c = cascade or TimeoutCascade()
    return httpx.Timeout(timeout=c.total, connect=c.connect, read=c.read, write=c.write, pool=c.pool)


async def retry_with_budget(
    request_fn: Callable[[], Any],
    max_retries: int = 2,
    backoff: float = 0.4,
) -> Any:
    """Execute async network operation with retry budget and exponential backoff."""
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await request_fn()
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as err:
            last_err = err
            if attempt < max_retries:
                await asyncio.sleep(backoff * (2 ** attempt))
            else:
                raise last_err
        except Exception as err:
            raise err
