"""
Shared HTTP Client connection pool singleton for unshorten-cli.

Prevents TCP port exhaustion and per-IP rate limits during high concurrency
batch resolution. One client is kept per event loop so Jupyter / FastAPI /
CLI workers do not share a closed loop.
"""

from __future__ import annotations

import asyncio
import os
import weakref
from typing import Dict, Optional

import httpx

_CLIENTS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_LOCKS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


DEFAULT_VERIFY_SSL = _env_bool("UNSHORTEN_VERIFY_SSL", False)
DEFAULT_HTTP2 = _env_bool("UNSHORTEN_HTTP2", True)
DEFAULT_USER_AGENT = os.environ.get(
    "UNSHORTEN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)


def build_default_limits() -> httpx.Limits:
    """Connection-pool limits for the shared client."""
    return httpx.Limits(
        max_connections=max(10, _env_int("UNSHORTEN_MAX_CONNECTIONS", 100)),
        max_keepalive_connections=max(5, _env_int("UNSHORTEN_MAX_KEEPALIVE", 50)),
        keepalive_expiry=_env_float("UNSHORTEN_KEEPALIVE_EXPIRY", 30.0),
    )


def _default_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        _env_float("UNSHORTEN_HTTP_TIMEOUT", 12.0),
        connect=_env_float("UNSHORTEN_HTTP_CONNECT", 3.0),
        read=_env_float("UNSHORTEN_HTTP_READ", 8.0),
    )


def _default_headers() -> Dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _lock_for(loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
    lock = _LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[loop] = lock
    return lock


def _build_client(timeout: Optional[httpx.Timeout], http2: bool) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        verify=DEFAULT_VERIFY_SSL,
        follow_redirects=False,
        limits=build_default_limits(),
        timeout=timeout or _default_timeout(),
        http2=http2,
        headers=_default_headers(),
    )


async def get_shared_client(timeout: Optional[httpx.Timeout] = None) -> httpx.AsyncClient:
    """
    Retrieve or create the shared AsyncClient for the current event loop.

    `timeout` is applied only when a new client is created. An already-open
    client is reused as-is so callers do not thrash the pool.
    """
    loop = asyncio.get_running_loop()
    existing = _CLIENTS.get(loop)
    if existing is not None and not existing.is_closed:
        return existing

    async with _lock_for(loop):
        existing = _CLIENTS.get(loop)
        if existing is not None and not existing.is_closed:
            return existing

        client: Optional[httpx.AsyncClient] = None
        if DEFAULT_HTTP2:
            try:
                client = _build_client(timeout, http2=True)
            except Exception:
                client = None
        if client is None:
            client = _build_client(timeout, http2=False)
        _CLIENTS[loop] = client
        return client


async def close_shared_client() -> None:
    """Gracefully close the shared AsyncClient for the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    async with _lock_for(loop):
        client = _CLIENTS.get(loop)
        if client is not None and not client.is_closed:
            try:
                await client.aclose()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        if loop in _CLIENTS:
            del _CLIENTS[loop]


async def close_all_shared_clients() -> None:
    """Close every loop-bound shared client. Used at process shutdown."""
    items = list(_CLIENTS.items())
    for loop, client in items:
        if client is None or client.is_closed:
            continue
        try:
            await client.aclose()
        except asyncio.CancelledError:
            raise
        except Exception:
            continue
        try:
            del _CLIENTS[loop]
        except Exception:
            pass
