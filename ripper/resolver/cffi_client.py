"""
High-Performance Stealth HTTP Adapter for Ripper Resolver using curl_cffi.
Impersonates Chrome 124 browser TLS/JA3/JA4 fingerprints and HTTP/2 settings.
Provides seamless drop-in compatibility with httpx.AsyncClient.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ripper.resolver.cffi_client")

try:
    from curl_cffi.requests import AsyncSession
    HAVE_CURL_CFFI = True
except ImportError:
    AsyncSession = None  # type: ignore
    HAVE_CURL_CFFI = False


class CurlCffiClientAdapter:
    """
    Adapter wrapping curl_cffi AsyncSession with Chrome 124 browser impersonation.
    Exposes get(), post(), head(), aclose() matching httpx.AsyncClient interface.
    """

    def __init__(
        self,
        impersonate: str = "chrome124",
        proxy: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        verify: bool = False,
    ) -> None:
        if not HAVE_CURL_CFFI:
            raise RuntimeError("curl_cffi is required for CurlCffiClientAdapter")
        self.impersonate = impersonate
        self.timeout = timeout
        self.verify = verify
        self._session = AsyncSession(
            impersonate=impersonate,
            verify=verify,
            timeout=timeout,
            proxies=proxy if proxy else None,
        )

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        follow_redirects: bool = True,
        **kwargs: Any,
    ) -> Any:
        return await self._session.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout or self.timeout,
            allow_redirects=follow_redirects,
        )

    async def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        follow_redirects: bool = True,
        **kwargs: Any,
    ) -> Any:
        return await self._session.post(
            url,
            data=data,
            json=json,
            headers=headers,
            timeout=timeout or self.timeout,
            allow_redirects=follow_redirects,
        )

    async def head(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        h = dict(headers or {})
        h["Range"] = "bytes=0-0"
        return await self._session.get(
            url,
            headers=h,
            timeout=timeout or self.timeout,
            allow_redirects=True,
        )

    async def aclose(self) -> None:
        try:
            await self._session.close()
        except Exception:
            pass

    async def __aenter__(self) -> "CurlCffiClientAdapter":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()
