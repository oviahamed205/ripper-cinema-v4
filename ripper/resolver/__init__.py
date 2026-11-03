"""
Ripper Resolver Package.
Exposes the modular Mother ResolverEngine and full backwards-compatible
API functions required across the Ripper codebase.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .base import BaseResolverHandler, ResolutionContext, make_hop
from .registry import HandlerRegistry, GLOBAL_REGISTRY
from .engine import ResolverEngine, GLOBAL_ENGINE
from ..models import UnshortenResult, HopInfo, ServerMirror

from .core import (
    DEFAULT_USER_AGENT,
    extract_url_from_query_params,
    extract_meta_refresh_url,
    extract_js_redirect_url,
    extract_filename_from_url_or_headers,
    extract_embedded_b64_url,
    extract_embedded_hex_url,
    extract_embedded_encoded_url,
    is_bot_challenge,
    is_circuit_open,
    record_domain_failure,
    record_domain_success,
    validate_presigned_url,
    probe_mirror_latency,
    pick_fastest_live_mirror,
    request_capped,
    request_capped_with_client,
    FetchResult,
)

from .handlers import (
    crawl_intermediate_server_page,
    resolve_to_direct_stream_url,
    extract_server_options_from_html,
    extract_cloud_urls_from_html,
    resolve_kmhd_page,
    resolve_vcloud_page,
    resolve_magiclinks_page,
    resolve_nexdrive_page,
    resolve_olamovies_page,
)


async def unshorten_url(
    target_url: str,
    max_hops: int = 15,
    timeout: float = 12.0,
    user_agent: str = DEFAULT_USER_AGENT,
    follow_js: bool = True,
    use_cache: bool = True,
    **kwargs: Any,
) -> UnshortenResult:
    """Primary asynchronous unshortener entrypoint."""
    engine = kwargs.get("engine") or ResolverEngine(max_depth=max_hops, timeout=timeout)
    extra_headers = kwargs.get("headers") or {}
    if user_agent and "User-Agent" not in extra_headers:
        extra_headers["User-Agent"] = user_agent
    return await engine.resolve(target_url, extra_headers=extra_headers, use_cache=use_cache)


def unshorten_url_sync(
    target_url: str,
    **kwargs: Any,
) -> UnshortenResult:
    """Synchronous wrapper for unshorten_url."""
    try:
        return asyncio.run(unshorten_url(target_url, **kwargs))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, unshorten_url(target_url, **kwargs)).result()


__all__ = [
    "ResolverEngine",
    "GLOBAL_ENGINE",
    "BaseResolverHandler",
    "ResolutionContext",
    "make_hop",
    "HandlerRegistry",
    "GLOBAL_REGISTRY",
    "unshorten_url",
    "unshorten_url_sync",
    "resolve_to_direct_stream_url",
    "crawl_intermediate_server_page",
    "extract_server_options_from_html",
    "extract_cloud_urls_from_html",
    "extract_url_from_query_params",
    "extract_meta_refresh_url",
    "extract_js_redirect_url",
    "extract_filename_from_url_or_headers",
    "extract_embedded_b64_url",
    "extract_embedded_hex_url",
    "extract_embedded_encoded_url",
    "is_bot_challenge",
    "resolve_kmhd_page",
    "resolve_magiclinks_page",
    "resolve_vcloud_page",
    "resolve_nexdrive_page",
    "resolve_olamovies_page",
    "is_circuit_open",
    "record_domain_failure",
    "record_domain_success",
    "validate_presigned_url",
    "probe_mirror_latency",
    "pick_fastest_live_mirror",
    "request_capped",
    "request_capped_with_client",
    "FetchResult",
    "DEFAULT_USER_AGENT",
]