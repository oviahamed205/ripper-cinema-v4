"""
Universal Bypasser Engine.
The primary orchestrator coordinating URL classification, ad-gate solvers,
FastForward declarative rules, container unrollers, Click'n'Load decryption, and fallback bridges.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import httpx

from ripper.universal_bypasser.adgates import (
    AdFlySolver,
    BaseAdGateSolver,
    BstlarSolver,
    CloudDriveGateSolver,
    DroplinkSolver,
    FastForwardRules,
    GenericFlySolver,
    GPLinksSolver,
    LinkvertiseSolver,
    OuoSolver,
    PasterSoSolver,
    PSAWfSolver,
    RocklinksSolver,
    ShareusSolver,
    ShrinkEarnSolver,
    Sub2UnlockSolver,
    Try2LinkSolver,
)
from ripper.universal_bypasser.bridges import CloudBypassBridge, PlaywrightInterceptor
from ripper.universal_bypasser.classifier import URLClassifier
from ripper.universal_bypasser.containers import (
    BaseContainerUnroller,
    DLCDecoder,
    FilecryptUnroller,
    KeeplinksUnroller,
    PastebinUnroller,
)
from ripper.universal_bypasser.models import (
    BypassContext,
    ContainerResult,
    GateType,
    ShortlinkResult,
)


class UniversalBypasserEngine:
    """Master orchestrator for resolving shortlinks and unrolling containers."""

    def __init__(self, context: Optional[BypassContext] = None):
        self.context = context or BypassContext()
        self._init_solvers()

    def _init_solvers(self):
        # Register specific adgate and locker solvers
        self.adgate_solvers: Dict[str, BaseAdGateSolver] = {
            "gplinks": GPLinksSolver(self.context),
            "droplink": DroplinkSolver(self.context),
            "rocklinks": RocklinksSolver(self.context),
            "ouo": OuoSolver(self.context),
            "sub2unlock": Sub2UnlockSolver(self.context),
            "shareus": ShareusSolver(self.context),
            "shrinkearn": ShrinkEarnSolver(self.context),
            "cloud_drive_gate": CloudDriveGateSolver(self.context),
            "generic_fly": GenericFlySolver(self.context),
            "linkvertise": LinkvertiseSolver(self.context),
            "adfly": AdFlySolver(self.context),
            "psa_wf": PSAWfSolver(self.context),
            "try2link": Try2LinkSolver(self.context),
            "bstlar": BstlarSolver(self.context),
        }

        # Register container unrollers
        self.container_unrollers: Dict[str, BaseContainerUnroller] = {
            "filecrypt": FilecryptUnroller(self.context),
            "keeplinks": KeeplinksUnroller(self.context),
            "pastebin": PastebinUnroller(self.context),
            "linkbox": PastebinUnroller(self.context),
            "paster_so": PasterSoSolver(self.context),
            "dlc_decoder": DLCDecoder(self.context),
        }

        # Bridges
        self.cloud_bridge = CloudBypassBridge(self.context)
        self.playwright_interceptor = PlaywrightInterceptor(self.context)

    async def _resolve_simple_redirect(self, url: str) -> ShortlinkResult:
        """Handles FastForward declarative rules, embedded parameters, or HTTP 30x direct redirects."""
        start_time = time.time()

        # Tier 1a: FastForward 400+ domain declarative rule table (<1ms)
        ff_target = FastForwardRules.match(url)
        if ff_target:
            return ShortlinkResult(
                original_url=url,
                resolved_url=ff_target,
                gate_type=GateType.SIMPLE_REDIRECT,
                success=True,
                duration=time.time() - start_time,
                solver_used="fastforward_declarative",
                intermediate_urls=[url, ff_target]
            )

        # Tier 1b: Embedded parameter extraction
        embedded = URLClassifier.extract_embedded_redirect(url)
        if embedded:
            return ShortlinkResult(
                original_url=url,
                resolved_url=embedded,
                gate_type=GateType.SIMPLE_REDIRECT,
                success=True,
                duration=time.time() - start_time,
                solver_used="embedded_param_unpack",
                intermediate_urls=[url, embedded]
            )

        # Tier 1c: HTTP head/get redirect follow
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": self.context.user_agent},
                follow_redirects=True,
                timeout=self.context.timeout,
                verify=False
            ) as client:
                resp = await client.head(url)
                final_url = str(resp.url)
                if final_url == url:
                    resp = await client.get(url)
                    final_url = str(resp.url)

                return ShortlinkResult(
                    original_url=url,
                    resolved_url=final_url,
                    gate_type=GateType.SIMPLE_REDIRECT,
                    success=True,
                    duration=time.time() - start_time,
                    solver_used="http_redirect_trace",
                    intermediate_urls=[url, final_url]
                )
        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=None,
                gate_type=GateType.SIMPLE_REDIRECT,
                success=False,
                duration=time.time() - start_time,
                solver_used="http_redirect_trace",
                error=str(e)
            )

    async def bypass_shortlink(self, url: str) -> ShortlinkResult:
        """Bypasses a single shortlink, ad-gate, or redirect URL."""
        # Check FastForward rules first for every URL
        ff_target = FastForwardRules.match(url)
        if ff_target:
            return ShortlinkResult(
                original_url=url,
                resolved_url=ff_target,
                gate_type=GateType.SIMPLE_REDIRECT,
                success=True,
                duration=0.001,
                solver_used="fastforward_declarative",
                intermediate_urls=[url, ff_target]
            )

        gate_type, handler_key = URLClassifier.classify(url)

        if gate_type == GateType.DIRECT_HOSTER:
            return ShortlinkResult(
                original_url=url,
                resolved_url=url,
                gate_type=GateType.DIRECT_HOSTER,
                success=True,
                duration=0.0,
                solver_used="direct_pass"
            )

        if gate_type == GateType.SIMPLE_REDIRECT:
            return await self._resolve_simple_redirect(url)

        if gate_type == GateType.AD_GATE:
            solver = self.adgate_solvers.get(handler_key, self.adgate_solvers["generic_fly"])
            res = await solver.solve(url)
            if res.success and res.resolved_url:
                return res

            # Fallback 1: Generic Fly solver if another failed
            if handler_key != "generic_fly":
                res2 = await self.adgate_solvers["generic_fly"].solve(url)
                if res2.success and res2.resolved_url:
                    return res2

            # Fallback 2: Cloud bridge
            if self.context.use_cloud_bridge:
                res_cloud = await self.cloud_bridge.solve(url)
                if res_cloud.success and res_cloud.resolved_url:
                    return res_cloud

            # Fallback 3: Playwright headless interceptor
            if self.context.use_playwright_fallback:
                return await self.playwright_interceptor.solve(url)

            return res

        if gate_type == GateType.CLOUD_GATE:
            # Check if Linkvertise solver handles it
            if handler_key == "linkvertise":
                lv_res = await self.adgate_solvers["linkvertise"].solve(url)
                if lv_res.success and lv_res.resolved_url:
                    return lv_res

            if self.context.use_cloud_bridge:
                res = await self.cloud_bridge.solve(url)
                if res.success and res.resolved_url:
                    return res

            if self.context.use_playwright_fallback:
                return await self.playwright_interceptor.solve(url)

        # Fallback for unknown URLs: try simple redirect trace
        return await self._resolve_simple_redirect(url)

    async def unroll_container(self, url: str) -> ContainerResult:
        """Unrolls a container or folder URL into individual hoster URLs."""
        gate_type, handler_key = URLClassifier.classify(url)
        unroller = self.container_unrollers.get(handler_key, self.container_unrollers["filecrypt"])
        return await unroller.unroll(url)

    async def resolve(self, url: str) -> Union[ShortlinkResult, ContainerResult]:
        """
        Unified resolution endpoint. Automatically detects whether the URL is
        a container/folder or a single shortlink, resolves chained gates, and
        returns the resulting ShortlinkResult or ContainerResult.
        """
        gate_type, handler_key = URLClassifier.classify(url)

        if gate_type == GateType.CONTAINER:
            return await self.unroll_container(url)

        # First resolve the shortlink
        short_res = await self.bypass_shortlink(url)
        if not short_res.success or not short_res.resolved_url:
            return short_res

        # Check if the resolved destination is actually a container!
        resolved_url = short_res.resolved_url
        dest_type, dest_key = URLClassifier.classify(resolved_url)
        if dest_type == GateType.CONTAINER:
            container_res = await self.unroll_container(resolved_url)
            container_res.metadata["original_shortlink"] = url
            return container_res

        return short_res
