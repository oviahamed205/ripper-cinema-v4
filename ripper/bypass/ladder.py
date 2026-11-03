"""
BypassLadder: Orchestrates escalating anti-bot bypass strategies (L0 -> L1 -> L2 -> L3).
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from .cookie_jar import GLOBAL_COOKIE_JAR
from .curl_client import CurlCffiClient
from .companion_bridge import CompanionBridge
from .headless import HeadlessSolver

log = logging.getLogger("ripper.bypass")

CLOUDFLARE_INDICATORS = (
    "cf-ray", "cf-cache-status", "cloudflare", "cf-browser-verification",
    "cf-turnstile", "checking your browser before accessing", "just a moment...",
)


def is_cloudflare_challenge(status_code: int, html: str, headers: Dict[str, str]) -> bool:
    """Return True if response appears to be a Cloudflare challenge or block."""
    if status_code in (403, 429, 503):
        low_html = html.lower()
        if any(k in low_html for k in CLOUDFLARE_INDICATORS):
            return True
        header_keys = [k.lower() for k in headers.keys()]
        if any("cf-" in k for k in header_keys):
            return True
    return False


class BypassLadder:
    """Escalating anti-bot resolver ladder."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.curl = CurlCffiClient(timeout=timeout)
        self.companion = CompanionBridge(timeout=timeout)
        self.headless = HeadlessSolver(timeout=timeout)

    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
        allow_headless: bool = False,
    ) -> Tuple[int, str, Dict[str, str]]:
        """
        Fetch URL escalating through bypass layers until a clean response is achieved.
        Returns (status_code, response_html, response_headers).
        """
        domain = urllib.parse.urlparse(url).netloc
        cached_cookies = GLOBAL_COOKIE_JAR.get_cookies_for_domain(domain)
        last_res: Optional[Tuple[int, str, Dict[str, str]]] = None

        # Level 0 & 1: High-Speed TLS Impersonation with cached clearance cookies
        if self.curl.is_available:
            try:
                status, text, resp_headers, _ = await self.curl.get(
                    url=url,
                    headers=headers,
                    cookies=cached_cookies,
                    proxy=proxy,
                )
                last_res = (status, text, resp_headers)
                if not is_cloudflare_challenge(status, text, resp_headers):
                    return status, text, resp_headers
            except Exception:
                pass

        # Level 2: Local Companion Solver Daemon (FlareSolverr/Turnstile Bridge)
        if await self.companion.is_companion_alive():
            res = await self.companion.solve(url, proxy=proxy)
            if res:
                status, text, _ = res
                return status, text, {}

        # Level 3: Stealth Headless Browser Fallback (only if explicitly allowed)
        if allow_headless:
            res = await self.headless.solve(url, proxy=proxy)
            if res:
                status, text, _ = res
                return status, text, {}

        # If previous challenge response exists, return it instead of making un-impersonated request
        if last_res is not None:
            return last_res

        # Fallback basic request if all else fails
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                return resp.status_code, resp.text, dict(resp.headers)
        except Exception as e:
            log.warning("Fallback fetch error for %s: %s", url, e)
            return 500, str(e), {}


# Global bypass ladder instance
GLOBAL_BYPASS = BypassLadder()