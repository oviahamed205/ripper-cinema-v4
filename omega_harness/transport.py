"""Shared async HTTP pool with per-destination limits and capped bodies.

TLS verification is always enabled. DNS checks reduce accidental private-network
access; they are NOT a DNS-rebinding-proof security boundary. Use an OS-level
network sandbox when processing hostile/untrusted sites.
"""
from __future__ import annotations
import asyncio
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit
import httpx
from .config import Config
from .models import Fetch


class FetchError(Exception):
    """Reason codes deliberately exclude possibly secret URLs and response bodies."""


class Transport:
    def __init__(self, config: Config, *, client: httpx.AsyncClient | None = None):
        self.config = config
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            verify=True, trust_env=False, follow_redirects=False,
            limits=httpx.Limits(max_connections=config.request_concurrency,
                               max_keepalive_connections=config.request_concurrency),
            timeout=config.request_timeout,
            headers={"User-Agent": "OmegaHarness/1.0 (authorized verification)",
                     "Accept-Encoding": "identity"})
        self.global_slots = asyncio.Semaphore(config.request_concurrency)
        self.host_slots: dict[str, asyncio.Semaphore] = {}
        self.stats = {"requests": 0, "bytes_sampled": 0, "active": 0, "peak_active": 0}
        self._host_cache: dict[str, float] = {}

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def _check_url(self, url: str):
        try:
            p = urlsplit(url)
            port = p.port
        except ValueError:
            raise FetchError("invalid_url") from None
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            raise FetchError("unsupported_or_credentialed_url")
        if self.config.allow_private_network:
            return
        host = p.hostname.lower()
        if self._host_cache.get(host, 0) > time.monotonic():
            return
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                infos = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
                    host, port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM),
                    timeout=self.config.request_timeout)
                addresses = [ipaddress.ip_address(item[4][0]) for item in infos]
            except (OSError, TimeoutError):
                raise FetchError("dns_failed") from None
        if not addresses or any(not ip.is_global for ip in addresses):
            raise FetchError("private_network_blocked")
        self._host_cache[host] = time.monotonic() + 30

    async def fetch(self, url: str, *, max_bytes: int, method: str = "GET",
                    headers: dict | None = None, follow_redirects: bool = True,
                    timeout=None, **kwargs) -> Fetch:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        current = url
        active_headers = dict(headers or {})
        active_headers["Accept-Encoding"] = "identity"
        started = time.perf_counter()
        for hop in range(self.config.redirect_limit + 1):
            await self._check_url(current)
            host = urlsplit(current).hostname.lower()
            semaphore = self.host_slots.setdefault(host, asyncio.Semaphore(self.config.per_host_concurrency))
            result = None
            for attempt in range(self.config.retries + 1):
                try:
                    # Host slot first: a busy host must not consume global permits.
                    async with semaphore, self.global_slots:
                        self.stats["active"] += 1
                        self.stats["peak_active"] = max(self.stats["peak_active"], self.stats["active"])
                        self.stats["requests"] += 1
                        try:
                            async with self.client.stream(method, current, headers=active_headers,
                                    timeout=timeout or self.config.request_timeout,
                                    follow_redirects=False, **kwargs) as response:
                                data = bytearray()
                                cap_reached = False
                                if not (follow_redirects and response.status_code in {301,302,303,307,308}):
                                    async for chunk in response.aiter_bytes(chunk_size=min(65536, max_bytes)):
                                        remaining = max_bytes - len(data)
                                        data.extend(chunk[:remaining])
                                        if len(data) >= max_bytes:
                                            cap_reached = True
                                            break
                                result = Fetch(str(response.url), response.status_code,
                                    {k.lower():v for k,v in response.headers.items()}, bytes(data),
                                    round((time.perf_counter()-started)*1000, 2), cap_reached)
                                self.stats["bytes_sampled"] += len(data)
                        finally:
                            self.stats["active"] -= 1
                except httpx.HTTPError:
                    if method != "GET" or attempt == self.config.retries:
                        raise FetchError("network_request_failed") from None
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                # Only idempotent GET retries; do not replay form submissions.
                if method == "GET" and result.status in {502,503,504} and attempt < self.config.retries:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
            assert result is not None
            if not follow_redirects or result.status not in {301,302,303,307,308}:
                return result
            location = result.headers.get("location")
            if not location:
                raise FetchError("redirect_without_location")
            if hop == self.config.redirect_limit:
                raise FetchError("redirect_limit")
            next_url = urljoin(current, location)
            old, new = urlsplit(current), urlsplit(next_url)
            if old.scheme == "https" and new.scheme != "https":
                raise FetchError("https_downgrade_blocked")
            if (old.scheme,old.hostname,old.port) != (new.scheme,new.hostname,new.port):
                active_headers = {k:v for k,v in active_headers.items()
                    if k.lower() not in {"authorization","cookie","proxy-authorization","referer","host"}}
            if result.status == 303 or (result.status in {301,302} and method == "POST"):
                method = "GET"
                for key in ("data","json","content","files"):
                    kwargs.pop(key,None)
            current = next_url
        raise FetchError("redirect_limit")


class ResolverClient:
    """httpx-like buffered client for existing resolver handlers.

    Intentionally no .stream method: legacy capped helpers use their .get fallback.
    All returned bodies are bounded by the harness HTML limit.
    """
    def __init__(self, transport: Transport):
        self.transport = transport

    async def _request(self, method, url, **kwargs):
        r = await self.transport.fetch(str(url), method=method,
            max_bytes=self.transport.config.max_html_bytes, **kwargs)
        h = {k:v for k,v in r.headers.items() if k not in {"content-encoding","transfer-encoding","content-length"}}
        return httpx.Response(r.status, headers=h, content=r.body,
                              request=httpx.Request(method, r.url))

    async def get(self,url,**kwargs): return await self._request("GET",url,**kwargs)
    async def post(self,url,**kwargs): return await self._request("POST",url,**kwargs)
    async def head(self,url,**kwargs): return await self._request("HEAD",url,**kwargs)
    async def aclose(self): pass  # transport lifecycle belongs to the runner
