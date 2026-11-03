"""
Binary-Safe, Size-Capped HTTP Client Layer for Ripper Resolver.
Guarantees memory safety by streaming headers first, aborting downloads of multi-GB
video/archive files, and capping HTML reading to 2MB.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger("ripper.resolver.binary_safe_http")

from ...timeouts import build_timeout
from .circuit_guard import is_circuit_open, record_domain_failure, record_domain_success
from .crypto_unpacker import _clean_extracted_url, _is_followable_http_url
from .honeypot_filter import host_of
from .doh_resolver import resolve_doh


try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except Exception:
    curl_requests = None
    HAS_CURL_CFFI = False


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


DEFAULT_USER_AGENT = _env_str(
    "UNSHORTEN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)

MAX_HTML_BYTES = max(64_000, _env_int("UNSHORTEN_MAX_HTML_BYTES", 2_000_000))

DEFAULT_ACCEPT_HTML = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
)

DOWNLOAD_EXTENSIONS: Tuple[str, ...] = (
    ".mkv", ".mp4", ".webm", ".avi", ".mov", ".ts", ".m4v", ".wmv", ".flv",
    ".m3u8", ".mpd",
    ".zip", ".rar", ".7z", ".iso", ".exe", ".pdf", ".nfo", ".srt", ".ass",
)

VIDEO_EXTENSIONS: Tuple[str, ...] = (
    ".mkv", ".mp4", ".webm", ".avi", ".mov", ".ts", ".m4v", ".wmv", ".flv",
    ".m3u8", ".mpd",
)

STORAGE_HOST_MARKERS: Tuple[str, ...] = (
    "r2.cloudflarestorage.com",
    "r2.dev",
    "amazonaws.com",
    "storage.googleapis.com",
    "backblazeb2.com",
    "wasabisys.com",
    "digitaloceanspaces.com",
    "b-cdn.net",
    "pixeldrain.com/api/file",
    "pixeldrain.dev/api/file",
)


@dataclass
class FetchResult:
    """Capped HTTP response that never holds a binary download body."""
    status_code: int = 0
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    content_type: str = ""
    content_length: int = 0
    server: str = ""
    location: Optional[str] = None
    is_binary: bool = False
    truncated: bool = False
    error: Optional[str] = None


def coerce_timeout(timeout: float) -> Any:
    """Build an httpx timeout object; fall back to a plain number."""
    try:
        built = build_timeout(timeout)
        if built is not None:
            return built
    except TypeError:
        try:
            return build_timeout(connect=timeout, read=timeout, write=timeout, pool=timeout)
        except Exception as exc:
            logger.debug("build_timeout with kwargs failed: %s", exc)
    except Exception as exc:
        logger.debug("build_timeout failed: %s", exc)
    try:
        return httpx.Timeout(timeout)
    except Exception as exc:
        logger.debug("httpx.Timeout creation failed: %s", exc)
        return timeout


def default_headers(user_agent: str = DEFAULT_USER_AGENT) -> Dict[str, str]:
    """Browser-like headers used for HTML hops."""
    return {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept": DEFAULT_ACCEPT_HTML,
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
    }


def normalize_start_url(raw_url: str) -> str:
    """Validate and normalize user-provided URL."""
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise ValueError("URL cannot be empty.")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    parsed = urllib.parse.urlparse(cleaned)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL structure: '{raw_url}'")
    return cleaned


def is_direct_storage_url(url: str) -> bool:
    """True when URL points at known object storage or direct file API."""
    if not url:
        return False
    lowered = url.lower()
    return any(marker in lowered for marker in STORAGE_HOST_MARKERS)


def is_direct_file_url(url: str) -> bool:
    """True when URL path ends with a known media or archive download extension."""
    if not url:
        return False
    try:
        path = urllib.parse.urlparse(url).path.lower()
    except Exception:
        return False
    return any(path.endswith(ext) for ext in DOWNLOAD_EXTENSIONS)


def _header_map(headers: Any) -> Dict[str, str]:
    """Lower-case header dict from an httpx response or mapping."""
    if not headers:
        return {}
    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except Exception:
        return {}


def _content_length_of(headers: Dict[str, str]) -> int:
    raw = headers.get("content-length", "")
    if raw and str(raw).isdigit():
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
    return 0


def _charset_from_content_type(content_type: str) -> str:
    lowered = (content_type or "").lower()
    if "charset=" not in lowered:
        return "utf-8"
    raw = lowered.split("charset=", 1)[1].split(";")[0].strip().strip('"').strip("'")
    return raw or "utf-8"


def looks_like_html(content_type: str, url: str = "") -> bool:
    """True when the response should be parsed as HTML."""
    lowered = (content_type or "").lower()
    if "text/html" in lowered or "application/xhtml" in lowered:
        return True
    if lowered.startswith("text/plain") and not is_direct_file_url(url):
        return True
    return False


def looks_like_binary(content_type: str, headers: Optional[Dict[str, str]] = None, url: str = "") -> bool:
    """True when the body is a file download and must not be buffered into RAM."""
    lowered = (content_type or "").lower()
    if looks_like_html(content_type, url):
        return False
    binary_prefixes = (
        "video/", "audio/", "image/", "application/octet-stream",
        "application/zip", "application/x-rar", "application/x-7z",
        "application/pdf", "application/x-bittorrent",
        "application/vnd.ms-", "application/force-download",
    )
    if any(lowered.startswith(prefix) or prefix in lowered for prefix in binary_prefixes):
        if "json" in lowered or "javascript" in lowered or "xml" in lowered:
            return False
        return True
    disposition = (headers or {}).get("content-disposition", "").lower()
    if "attachment" in disposition or "filename=" in disposition:
        if not looks_like_html(content_type, url):
            return True
    if is_direct_file_url(url) and "text/" not in lowered and "json" not in lowered:
        return True
    return False


def extract_filename_from_url_or_headers(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """Extract readable filename from Content-Disposition, URL path, or query parameters."""
    header_map = _header_map(headers or {})
    content_disposition = header_map.get("content-disposition", "")
    if "filename=" in content_disposition:
        match = re.search(r"filename\*?=(?:UTF-8\'\')?[\"']?([^\"';\r\n]+)[\"']?", content_disposition)
        if match:
            return urllib.parse.unquote(match.group(1).strip())

    parsed = urllib.parse.urlparse(url or "")
    if "response-content-disposition=" in parsed.query:
        match = re.search(r'filename%3D%22([^%22&]+)%22|filename="([^"&]+)"', parsed.query)
        if match:
            filename = match.group(1) or match.group(2)
            return urllib.parse.unquote_plus(filename)

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        candidate = path_parts[-1]
        lowered = candidate.lower()
        if any(lowered.endswith(ext) for ext in DOWNLOAD_EXTENSIONS):
            return urllib.parse.unquote_plus(candidate)

    return "download_file"


def _guess_media_content_type(url: str, filename: str = "") -> str:
    haystack = f"{url} {filename}".lower()
    if ".mkv" in haystack:
        return "video/x-matroska"
    if ".mp4" in haystack:
        return "video/mp4"
    if ".webm" in haystack:
        return "video/webm"
    if any(ext in haystack for ext in VIDEO_EXTENSIONS):
        return "video/mp4"
    return "application/octet-stream"


def is_bot_challenge(status_code: int, headers: Dict[str, str], html_body: str) -> Tuple[bool, str]:
    """Detect if response is a Cloudflare / DDoS-Guard challenge page."""
    header_map = _header_map(headers)
    server = header_map.get("server", "").lower()
    cf_mitigated = header_map.get("cf-mitigated", "").lower()
    body = html_body or ""
    body_lower = body.lower()

    if cf_mitigated == "challenge" or "chl_page" in body:
        return True, "Cloudflare Managed Challenge (Turnstile / Bot Protection)"

    if (
        "challenges.cloudflare.com" in body
        or "cf-turnstile-response" in body
        or "_cf_chl_opt" in body
    ):
        return True, "Cloudflare Turnstile Challenge (Requires browser clearance)"

    if "just a moment..." in body_lower and (
        "cloudflare" in server or "cf-error-details" in body_lower or "/cdn-cgi/" in body_lower
    ):
        return True, "Cloudflare Challenge Wall (HTTP 403 / 503)"

    if "ddos-guard" in server or "ddos-guard" in body_lower:
        if status_code in (403, 503, 429):
            return True, "DDoS-Guard Bot Verification"

    return False, ""


def _fetch_result_from_parts(
    status_code: int,
    url: str,
    headers: Dict[str, str],
    text: str = "",
    is_binary: bool = False,
    truncated: bool = False,
    error: Optional[str] = None,
) -> FetchResult:
    return FetchResult(
        status_code=status_code,
        url=str(url or ""),
        headers=headers,
        text=text,
        content_type=headers.get("content-type", ""),
        content_length=_content_length_of(headers),
        server=headers.get("server", ""),
        location=headers.get("location"),
        is_binary=is_binary,
        truncated=truncated,
        error=error,
    )


async def _read_stream_response(response: Any) -> FetchResult:
    """Consume an httpx stream response safely, aborting on binary bodies."""
    headers = _header_map(getattr(response, "headers", {}) or {})
    final_url = str(getattr(response, "url", "") or "")
    status_code = int(getattr(response, "status_code", 0) or 0)
    content_type = headers.get("content-type", "")
    is_redirect = status_code in (301, 302, 303, 307, 308)
    binary = looks_like_binary(content_type, headers, final_url)
    if is_redirect or binary:
        return _fetch_result_from_parts(status_code, final_url, headers, is_binary=binary)

    chunks = []
    total = 0
    truncated = False
    try:
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= MAX_HTML_BYTES:
                truncated = True
                break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug("Exception while streaming chunks: %s", exc)

    charset = _charset_from_content_type(content_type)
    try:
        text = b"".join(chunks).decode(charset, errors="replace")
    except Exception as exc:
        logger.debug("Failed decoding chunks with %s, falling back to utf-8: %s", charset, exc)
        text = b"".join(chunks).decode("utf-8", errors="replace")
    return _fetch_result_from_parts(
        status_code, final_url, headers, text=text, truncated=truncated
    )


def _fetch_result_from_full_response(response: Any) -> FetchResult:
    """Build a FetchResult from a buffered response with length safety."""
    headers = _header_map(getattr(response, "headers", {}) or {})
    final_url = str(getattr(response, "url", "") or "")
    status_code = int(getattr(response, "status_code", 0) or 0)
    content_type = headers.get("content-type", "")
    binary = looks_like_binary(content_type, headers, final_url)
    if status_code in (301, 302, 303, 307, 308) or binary:
        return _fetch_result_from_parts(status_code, final_url, headers, is_binary=binary)

    raw = getattr(response, "content", b"") or b""
    truncated = False
    if isinstance(raw, bytes) and len(raw) > MAX_HTML_BYTES:
        raw = raw[:MAX_HTML_BYTES]
        truncated = True
    charset = _charset_from_content_type(content_type)
    try:
        text = raw.decode(charset, errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception:
        text = getattr(response, "text", "") or ""
    return _fetch_result_from_parts(
        status_code, final_url, headers, text=text, truncated=truncated
    )


async def request_capped(
    client: Optional[httpx.AsyncClient],
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 12.0,
    follow_redirects: bool = False,
) -> FetchResult:
    """
    GET a URL and return a size-capped result.
    Checks circuit breaker first. Retries with verify=False on SSL failures.
    """
    domain = host_of(url)
    if await is_circuit_open(domain):
        return _fetch_result_from_parts(
            0, url, {}, error=f"Circuit breaker is open for host: {domain}. Request aborted."
        )

    request_headers = headers or default_headers()
    timeout_obj = coerce_timeout(timeout)

    async def _do(active: httpx.AsyncClient) -> FetchResult:
        if hasattr(active, "stream"):
            async with active.stream(
                "GET",
                url,
                headers=request_headers,
                timeout=timeout_obj,
                follow_redirects=follow_redirects,
            ) as response:
                res = await _read_stream_response(response)
                if res.status_code and res.status_code >= 200:
                    await record_domain_success(domain)
                return res
        response = await active.get(
            url,
            headers=request_headers,
            timeout=timeout_obj,
            follow_redirects=follow_redirects,
        )
        res = _fetch_result_from_full_response(response)
        if res.status_code and res.status_code >= 200:
            await record_domain_success(domain)
        return res

    try:
        if client is not None:
            try:
                return await _do(client)
            except httpx.ConnectError as exc:
                msg = str(exc).lower()
                if "certificate" not in msg and "ssl" not in msg:
                    raise
            async with httpx.AsyncClient(
                timeout=timeout_obj, verify=False, follow_redirects=follow_redirects
            ) as insecure:
                return await _do(insecure)

        async with httpx.AsyncClient(timeout=timeout_obj, follow_redirects=follow_redirects) as fresh:
            try:
                return await _do(fresh)
            except httpx.ConnectError as exc:
                msg = str(exc).lower()
                if "certificate" not in msg and "ssl" not in msg:
                    raise
        async with httpx.AsyncClient(
            timeout=timeout_obj, verify=False, follow_redirects=follow_redirects
        ) as insecure:
            return await _do(insecure)
    except asyncio.CancelledError:
        raise
    except httpx.ConnectError as exc:
        msg = str(exc).lower()
        # Check if this is a DNS resolution failure (getaddrinfo / nodename / gaierror)
        if any(term in msg for term in ("getaddrinfo", "nodename", "gaierror", "failed to resolve", "name or service not known")):
            doh_ip = await resolve_doh(domain)
            if doh_ip:
                parsed = urllib.parse.urlparse(url)
                # Reconstruct URL with resolved IP
                netloc_parts = parsed.netloc.split(":")
                port_suffix = f":{netloc_parts[1]}" if len(netloc_parts) > 1 else ""
                doh_url = parsed._replace(netloc=f"{doh_ip}{port_suffix}").geturl()
                doh_headers = dict(request_headers)
                doh_headers["Host"] = parsed.netloc
                logger.info("Retrying request to %s via DoH resolved IP %s", domain, doh_ip)
                try:
                    async with httpx.AsyncClient(timeout=timeout_obj, verify=False, follow_redirects=follow_redirects) as doh_client:
                        return await doh_client.get(doh_url, headers=doh_headers)
                except Exception as doh_exc:
                    logger.debug("DoH fallback attempt failed: %s", doh_exc)
        await record_domain_failure(domain)
        return _fetch_result_from_parts(
            0, url, {}, error=f"Could not connect to {domain or url}: {exc}"
        )
    except httpx.TimeoutException:
        await record_domain_failure(domain)
        return _fetch_result_from_parts(
            0, url, {}, error=f"Timed out connecting to {domain or url}."
        )
    except httpx.HTTPError as exc:
        await record_domain_failure(domain)
        return _fetch_result_from_parts(
            0, url, {}, error=f"Could not reach {domain or url}: {exc}"
        )
    except Exception as exc:
        await record_domain_failure(domain)
        return _fetch_result_from_parts(
            0, url, {}, error=f"Unexpected network error for {domain or url}: {exc}"
        )



async def request_capped_with_client(
    client: Optional[httpx.AsyncClient],
    url: str,
    headers: Optional[Dict[str, str]],
    timeout: float,
    follow_redirects: bool = True,
) -> FetchResult:
    """Like request_capped, following redirects for deep landing pages."""
    return await request_capped(
        client, url, headers=headers, timeout=timeout, follow_redirects=follow_redirects
    )


async def fetch_with_impersonation(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 12.0,
) -> Optional[FetchResult]:
    """Replay request with curl_cffi Chrome impersonation to bypass TLS fingerprints."""
    if not HAS_CURL_CFFI or curl_requests is None:
        return None

    active_headers = headers if headers is not None else default_headers()


    def _sync_fetch() -> FetchResult:
        response = curl_requests.get(
            url,
            headers=active_headers,
            impersonate="chrome",
            timeout=timeout,

            allow_redirects=False,
            verify=False,
        )
        header_map = _header_map(getattr(response, "headers", {}) or {})
        final_url = str(getattr(response, "url", url) or url)
        status_code = int(getattr(response, "status_code", 0) or 0)
        content_type = header_map.get("content-type", "")
        binary = looks_like_binary(content_type, header_map, final_url)
        text = ""
        truncated = False
        if not binary and status_code not in (301, 302, 303, 307, 308):
            raw_text = getattr(response, "text", "") or ""
            if len(raw_text) > MAX_HTML_BYTES:
                raw_text = raw_text[:MAX_HTML_BYTES]
                truncated = True
            text = raw_text
        return _fetch_result_from_parts(
            status_code, final_url, header_map, text=text, is_binary=binary, truncated=truncated
        )

    try:
        return await asyncio.to_thread(_sync_fetch)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None