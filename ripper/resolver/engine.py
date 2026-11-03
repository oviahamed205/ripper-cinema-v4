"""
Mother Resolver Engine for Ripper CLI.
Orchestrates recursive unshortening, site-specific plugin delegation,
redirect loop guards, binary stream detection, and pre-flight validation.
"""
from __future__ import annotations

import asyncio
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..models import HopInfo, UnshortenResult, SafetyReport, ServerMirror
from ..safety import analyze_destination_safety
from ..cache import GLOBAL_CACHE
from ..http_client import get_shared_client
from .base import ResolutionContext, make_hop
from .registry import GLOBAL_REGISTRY
from .core import (
    is_circuit_open,
    is_direct_file_url,
    is_direct_storage_url,
    validate_presigned_url,
    pick_fastest_live_mirror,
    DOWNLOAD_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from . import handlers  # Ensures all handlers are registered in GLOBAL_REGISTRY


class ResolverEngine:
    """The central unshortening and link gateway engine."""

    def __init__(self, max_depth: int = 25, timeout: float = 30.0, universal_engine: Optional[Any] = None) -> None:
        self.max_depth = max_depth
        self.timeout = timeout
        self._universal_engine = universal_engine

    def _get_universal_engine(self):
        if self._universal_engine is None:
            from ripper.universal_bypasser import UniversalBypasserEngine
            self._universal_engine = UniversalBypasserEngine()
        return self._universal_engine

    async def resolve(
        self,
        url: str,
        extra_headers: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
        client: Optional[Any] = None,
        max_hops: Optional[int] = None,
    ) -> UnshortenResult:
        clean_url = (url or "").strip()
        if not clean_url:
            return self._empty_result("", "URL cannot be empty.")

        if not clean_url.startswith(("http://", "https://")):
            clean_url = "https://" + clean_url

        # Cache fast-path
        if use_cache and GLOBAL_CACHE:
            try:
                cached = await GLOBAL_CACHE.get("resolution", clean_url)
                if cached:
                    return cached
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Cache read failed: %s", exc)

        t0 = time.monotonic()
        depth_limit = max_hops if max_hops is not None else self.max_depth
        context = ResolutionContext(
            max_depth=depth_limit,
            timeout=self.timeout,
            extra_headers=extra_headers or {},
        )

        current_url = clean_url
        context.visited_urls.add(current_url)

        http_client = client if client is not None else await get_shared_client()
        hops: List[HopInfo] = []
        final_url = current_url
        server_mirrors: List[ServerMirror] = []
        error_message: Optional[str] = None

        for depth in range(depth_limit):
            context.depth = depth

            # Check circuit breaker on domain
            domain = urllib.parse.urlparse(current_url).netloc.lower()
            if await is_circuit_open(domain):
                hops.append(make_hop(
                    url=current_url,
                    status_code=503,
                    redirect_type="circuit_open",
                    extra_details=f"Fast-failing request: circuit breaker is active for {domain}",
                    hop_number=len(hops) + 1,
                ))
                error_message = f"Circuit open: circuit breaker active for {domain}"
                break

            # Fast-path: Direct Media / Archive file extension or Storage URL
            if is_direct_file_url(current_url) or is_direct_storage_url(current_url):
                hops.append(make_hop(
                    url=current_url,
                    status_code=200,
                    redirect_type="final_media_stream",
                    extra_details="Direct playable media or storage stream reached",
                    hop_number=len(hops) + 1,
                ))
                final_url = current_url
                break

            # -------------------------------------------------------------
            # BACKEND AUTO-DETECTION: Universal Shortlink & Container Engine
            # -------------------------------------------------------------
            from ripper.universal_bypasser.classifier import URLClassifier
            from ripper.universal_bypasser.adgates.fastforward_rules import FastForwardRules
            from ripper.universal_bypasser.models import GateType, ShortlinkResult, ContainerResult

            is_ff = bool(FastForwardRules.match(current_url))
            gate_type, handler_key = URLClassifier.classify(current_url)

            if is_ff or gate_type in (GateType.AD_GATE, GateType.CONTAINER, GateType.CLOUD_GATE):
                u_engine = self._get_universal_engine()
                u_res = await u_engine.resolve(current_url)
                if isinstance(u_res, ContainerResult) and u_res.success and u_res.unlocked_urls:
                    for u in u_res.unlocked_urls:
                        server_mirrors.append(ServerMirror(
                            label=u_res.title or "Container Link",
                            intermediate_url=u,
                            direct_download_url=u,
                        ))
                    hops.append(make_hop(
                        url=current_url,
                        status_code=200,
                        redirect_type="container_unroll",
                        extra_details=f"Universal bypasser unrolled {len(u_res.unlocked_urls)} link(s): {u_res.title or ''}",
                        hop_number=len(hops) + 1,
                    ))
                    next_url = u_res.unlocked_urls[0]
                    context.visited_urls.add(next_url)
                    current_url = next_url
                    final_url = next_url
                    continue
                elif isinstance(u_res, ShortlinkResult) and u_res.success and u_res.resolved_url:
                    hops.append(make_hop(
                        url=current_url,
                        status_code=200,
                        redirect_type=f"shortlink_bypass:{u_res.solver_used or 'auto'}",
                        extra_details=f"Auto-bypassed shortlink ({u_res.duration:.2f}s) -> {u_res.resolved_url}",
                        hop_number=len(hops) + 1,
                    ))
                    next_url = u_res.resolved_url
                    if next_url != current_url:
                        context.visited_urls.add(next_url)
                        current_url = next_url
                        final_url = next_url
                        continue

            # Delegate to registered site handlers in priority order
            handler = GLOBAL_REGISTRY.get_handler(current_url)
            if not handler:
                # Fallback: check if universal engine can trace/bypass unknown gateway
                u_engine = self._get_universal_engine()
                u_res = await u_engine.bypass_shortlink(current_url)
                if u_res.success and u_res.resolved_url and u_res.resolved_url != current_url:
                    hops.append(make_hop(
                        url=current_url,
                        status_code=200,
                        redirect_type=f"generic_bypass:{u_res.solver_used or 'auto'}",
                        extra_details=f"Bypassed unknown gateway ({u_res.duration:.2f}s) -> {u_res.resolved_url}",
                        hop_number=len(hops) + 1,
                    ))
                    next_url = u_res.resolved_url
                    context.visited_urls.add(next_url)
                    current_url = next_url
                    final_url = next_url
                    continue
                break

            step_result = await handler.resolve(current_url, http_client, context)
            if not step_result:
                final_url = current_url
                break

            next_url, step_hops = step_result
            hops.extend(step_hops)

            # Collect mirrors if handler supports it
            if hasattr(handler, "extract_mirrors"):
                try:
                    extracted = handler.extract_mirrors("", current_url)
                    if extracted:
                        server_mirrors.extend(extracted)
                except Exception as exc:
                    logger.debug("Failed to extract mirrors for %s: %s", current_url, exc)

            if not next_url or next_url == current_url:
                final_url = current_url
                break

            # Loop detection guard
            if next_url in context.visited_urls:
                hops.append(make_hop(
                    url=next_url,
                    status_code=310,
                    redirect_type="loop_detected",
                    extra_details="Redirect cycle detected; terminating traversal.",
                    hop_number=len(hops) + 1,
                ))
                error_message = f"Redirect loop detected at: {next_url}"
                final_url = next_url
                break

            context.visited_urls.add(next_url)
            current_url = next_url
            final_url = next_url

        # Pre-flight stream validation on final cloud stream if direct storage
        if is_direct_storage_url(final_url) and not error_message:
            alive = await validate_presigned_url(final_url, client=http_client, timeout=3.0)
            if not alive and server_mirrors:
                # If primary is dead, race alternative mirrors
                fastest = await pick_fastest_live_mirror(server_mirrors, client=http_client, timeout=3.0)
                if fastest and fastest != final_url:
                    final_url = fastest
                    hops.append(make_hop(
                        url=fastest,
                        status_code=200,
                        redirect_type="mirror_failover",
                        extra_details="Primary stream expired/unreachable; failed over to live mirror",
                        hop_number=len(hops) + 1,
                    ))

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        safety_report = analyze_destination_safety(final_url)

        # Record hop sequence into Speculative Markov Hop Predictor
        if len(hops) >= 2:
            try:
                from .core.speculative_hop import GLOBAL_HOP_PREDICTOR
                chain_urls = [clean_url] + [h.url for h in hops if h.url]
                GLOBAL_HOP_PREDICTOR.record_chain(chain_urls)
            except Exception as exc:
                logger.debug("Hop transition record skipped: %s", exc)

        result = UnshortenResult(
            original_url=clean_url,
            final_url=final_url,
            total_hops=len(hops),
            total_time_ms=elapsed_ms,
            hops=hops,
            safety=safety_report,
            server_mirrors=server_mirrors,
            is_success=error_message is None,
            error_message=error_message,
        )

        if use_cache and GLOBAL_CACHE and result.is_success:
            try:
                await GLOBAL_CACHE.set("resolution", clean_url, result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Resolution cache save failed: %s", exc)

        return result

    def _empty_result(self, original_url: str, error_message: str) -> UnshortenResult:
        hop = make_hop(
            url=original_url,
            status_code=0,
            redirect_type="unresolved",
            extra_details=error_message,
            hop_number=1,
        )
        safety = analyze_destination_safety(original_url)
        return UnshortenResult(
            original_url=original_url,
            final_url=original_url,
            total_hops=1,
            total_time_ms=0.0,
            hops=[hop],
            safety=safety,
            server_mirrors=[],
            is_success=False,
            error_message=error_message,
        )

    # Alias for API compatibility
    resolve_url = resolve


GLOBAL_ENGINE = ResolverEngine()


async def unshorten_url(
    url: str,
    client: Optional[Any] = None,
    max_hops: int = 25,
    timeout: float = 20.0,
    use_cache: bool = True,
    extra_headers: Optional[Dict[str, str]] = None,
) -> UnshortenResult:
    """Async entrypoint to resolve shortlink to final destination."""
    return await GLOBAL_ENGINE.resolve(
        url,
        extra_headers=extra_headers,
        use_cache=use_cache,
    )



def unshorten_url_sync(
    url: str,
    client: Optional[Any] = None,
    max_hops: int = 25,
    timeout: float = 20.0,
    use_cache: bool = True,
    extra_headers: Optional[Dict[str, str]] = None,
) -> UnshortenResult:
    """Synchronous convenience wrapper for unshorten_url."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(
                lambda: asyncio.run(
                    GLOBAL_ENGINE.resolve(
                        url,
                        use_cache=use_cache,
                        extra_headers=extra_headers,
                    )
                )
            ).result()

    return asyncio.run(
        GLOBAL_ENGINE.resolve(
            url,
            use_cache=use_cache,
            extra_headers=extra_headers,
        )
    )
