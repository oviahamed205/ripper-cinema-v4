"""
L0: High-speed curl_cffi TLS JA3/JA4 Impersonation Client.
Handles 85% of Cloudflare bot protection gates directly via TLS Chrome 124 impersonation.
"""
from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any, Dict, Optional, Tuple

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CURL_CFFI = False

from .cookie_jar import GLOBAL_COOKIE_JAR

DEFAULT_IMPERSONATE = "chrome124"
FALLBACK_IMPERSONATE = "safari17_0"


class CurlCffiClient:
    """Async wrapper around curl_cffi for direct TLS fingerprint spoofing."""

    def __init__(self, impersonate: str = DEFAULT_IMPERSONATE, timeout: float = 20.0) -> None:
        self.impersonate = impersonate
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        return HAS_CURL_CFFI

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        proxy: Optional[str] = None,
    ) -> Tuple[int, str, Dict[str, str], Dict[str, str]]:
        """
        Execute request using TLS impersonation.
        Returns (status_code, text_content, response_headers, response_cookies).
        """
        if not HAS_CURL_CFFI:
            raise RuntimeError("curl_cffi is not installed; cannot perform TLS impersonation.")

        domain = urllib.parse.urlparse(url).netloc
        all_cookies = GLOBAL_COOKIE_JAR.get_cookies_for_domain(domain)
        if cookies:
            all_cookies.update(cookies)

        proxies = {"http": proxy, "https": proxy} if proxy else None

        loop = asyncio.get_event_loop()

        def _do_req() -> Any:
            sess = cffi_requests.Session(impersonate=self.impersonate)
            try:
                resp = sess.get(
                    url,
                    headers=headers,
                    cookies=all_cookies,
                    proxies=proxies,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                resp_cookies = {k: v for k, v in resp.cookies.items()}
                # Save any new clearance cookies
                if any(k.startswith(("cf_", "__cf")) for k in resp_cookies):
                    GLOBAL_COOKIE_JAR.set_cookies_for_domain(domain, resp_cookies)
                return resp.status_code, resp.text, dict(resp.headers), resp_cookies
            finally:
                sess.close()

        return await loop.run_in_executor(None, _do_req)