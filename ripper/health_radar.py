"""
Autonomous Server Health & Speed Ranker for unshorten-cli.
Maintains a live latency and throughput scoreboard for all cloud storage mirrors
(VegaCloud, PixelDrain, HubCloud, Cloudflare Worker R2, GoFile).
"""

from __future__ import annotations

import time
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import httpx


@dataclass
class MirrorScore:
    url: str
    host: str
    latency_ms: float
    is_alive: bool
    status_code: int


class HealthRadar:
    def __init__(self):
        self._history: Dict[str, float] = {}  # host -> avg_latency_ms

    async def race_mirrors(
        self,
        urls: List[str],
        timeout: float = 2.5,
        max_probe_concurrency: int = 8,
    ) -> List[MirrorScore]:
        """
        Probe all candidate mirrors concurrently with 1-byte Range requests.
        Returns sorted list of MirrorScores from fastest to slowest.
        """
        if not urls:
            return []

        scores: List[MirrorScore] = []
        limits = httpx.Limits(max_connections=20)

        async with httpx.AsyncClient(timeout=timeout, verify=False, follow_redirects=True, limits=limits) as client:
            async def probe(u: str) -> MirrorScore:
                from urllib.parse import urlparse
                host = urlparse(u).netloc or u
                t0 = time.time()
                try:
                    r = await client.get(
                        u,
                        headers={"Range": "bytes=0-0", "User-Agent": "Mozilla/5.0"},
                        timeout=timeout,
                    )
                    lat = (time.time() - t0) * 1000.0
                    alive = r.status_code in (200, 206, 302, 307)
                    if alive:
                        self._history[host] = lat
                    return MirrorScore(url=u, host=host, latency_ms=lat, is_alive=alive, status_code=r.status_code)
                except Exception:
                    return MirrorScore(url=u, host=host, latency_ms=9999.0, is_alive=False, status_code=0)

            tasks = [probe(u) for u in urls[:max_probe_concurrency]]
            results = await asyncio.gather(*tasks)
            # Sort: alive first, then lowest latency
            scores = sorted(results, key=lambda s: (not s.is_alive, s.latency_ms))

        return scores

    def pick_fastest_url(self, scores: List[MirrorScore]) -> Optional[str]:
        for s in scores:
            if s.is_alive and s.latency_ms < 9999.0:
                return s.url
        return scores[0].url if scores else None


HEALTH_RADAR = HealthRadar()
