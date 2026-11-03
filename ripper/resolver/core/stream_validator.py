"""
Pre-Flight Stream Validator & Multi-Mirror Latency Race Engine for Ripper Resolver.
Validates that presigned object storage URLs (R2, S3, Wasabi) are ALIVE and not expired
using HTTP 206 Range: bytes=0-0 probes, preventing broken streams from reaching player/downloader.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional, Sequence, Tuple

import httpx

logger = logging.getLogger("ripper.resolver.stream_validator")

from ...models import ServerMirror
from .binary_safe_http import coerce_timeout
from .crypto_unpacker import _is_followable_http_url


PRESIGN_CHECK_TIMEOUT = 3.0


async def validate_presigned_url(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 3.0,
) -> bool:
    """
    Probe a presigned link without downloading the payload.
    HEAD 200 is success. If HEAD is blocked or ambiguous, a 1-byte Range GET
    probe is used. 404/410/expired-403 are marked dead (False).
    """
    if not url or not _is_followable_http_url(url):
        return False

    timeout_obj = coerce_timeout(min(timeout, PRESIGN_CHECK_TIMEOUT) if timeout else PRESIGN_CHECK_TIMEOUT)

    async def _probe(active: httpx.AsyncClient) -> bool:
        try:
            head = await active.head(url, timeout=timeout_obj, follow_redirects=True)
            if head.status_code == 200:
                return True
            if head.status_code in (404, 410):
                return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("HEAD probe failed for %s, trying ranged GET: %s", url, exc)

        try:
            ranged = await active.get(
                url,
                headers={"Range": "bytes=0-0"},
                timeout=timeout_obj,
                follow_redirects=True,
            )
            if ranged.status_code in (200, 206):
                return True
            if ranged.status_code in (403, 404, 410):
                return False
        except asyncio.CancelledError:
            raise
        except Exception:
            return True
        return True

    try:
        if client is not None:
            return await _probe(client)
        async with httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True) as fresh:
            return await _probe(fresh)
    except asyncio.CancelledError:
        raise
    except Exception:
        return True


async def probe_mirror_latency(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 2.5,
) -> Tuple[str, float, bool]:
    """Measure round-trip latency to a mirror using a 1-byte Range request."""
    if not url or not _is_followable_http_url(url):
        return url, 9999.0, False

    t0 = time.monotonic()
    timeout_obj = coerce_timeout(timeout)

    async def _do(active: httpx.AsyncClient) -> Tuple[str, float, bool]:
        try:
            r = await active.get(
                url,
                headers={"Range": "bytes=0-0"},
                timeout=timeout_obj,
                follow_redirects=True,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            is_alive = r.status_code in (200, 206, 302, 307)
            return url, latency_ms, is_alive
        except asyncio.CancelledError:
            raise
        except Exception:
            return url, 9999.0, False

    try:
        if client is not None:
            return await _do(client)
        async with httpx.AsyncClient(timeout=timeout_obj, follow_redirects=True) as fresh:
            return await _do(fresh)
    except asyncio.CancelledError:
        raise
    except Exception:
        return url, 9999.0, False


async def pick_fastest_live_mirror(
    mirrors: Sequence[ServerMirror],
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 3.0,
) -> Optional[str]:
    """
    Concurrent Multi-Mirror Latency Race Engine.
    Probes all candidate direct URLs in parallel and returns the lowest-latency live mirror.
    """
    candidates = [
        getattr(m, "direct_download_url", None)
        for m in mirrors
        if getattr(m, "direct_download_url", None)
    ]
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    tasks = [probe_mirror_latency(u, client=client, timeout=min(timeout, 2.5)) for u in candidates[:8]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    live_mirrors: List[Tuple[str, float]] = []
    for item in results:
        if isinstance(item, tuple) and len(item) == 3:
            u, lat, alive = item
            if alive:
                live_mirrors.append((u, lat))

    if live_mirrors:
        live_mirrors.sort(key=lambda x: x[1])
        return live_mirrors[0][0]

    return candidates[0]