"""
L2: Companion Microservice Bridge for FlareSolverr or Local Turnstile Solvers.
Probes local daemon (http://127.0.0.1:8191/v1) for zero-overhead challenge solving.
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, Optional, Tuple
import httpx

from .cookie_jar import GLOBAL_COOKIE_JAR

COMPANION_URL = "http://127.0.0.1:8191/v1"


class CompanionBridge:
    """Communicates with local anti-bot companion service if running."""

    def __init__(self, endpoint: str = COMPANION_URL, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    async def is_companion_alive(self) -> bool:
        """Check if companion solver service is reachable on localhost."""
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                resp = await client.get(self.endpoint.replace("/v1", "/"))
                return resp.status_code in (200, 404, 405)
        except Exception:
            return False

    async def solve(
        self,
        url: str,
        proxy: Optional[str] = None,
    ) -> Optional[Tuple[int, str, Dict[str, str]]]:
        """
        Request companion solver to navigate and solve Cloudflare/Turnstile challenge.
        Returns (status_code, response_html, clearance_cookies) or None if solver offline.
        """
        payload: Dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": int(self.timeout * 1000),
        }
        if proxy:
            payload["proxy"] = {"url": proxy}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    solution = data.get("solution", {})
                    html = solution.get("response", "")
                    status = solution.get("status", 200)
                    raw_cookies = solution.get("cookies", [])
                    cookies_dict = {c["name"]: c["value"] for c in raw_cookies if "name" in c and "value" in c}

                    domain = urllib.parse.urlparse(url).netloc
                    if cookies_dict:
                        GLOBAL_COOKIE_JAR.set_cookies_for_domain(domain, cookies_dict)

                    return status, html, cookies_dict
        except Exception:
            pass

        return None