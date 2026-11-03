"""
Playwright Headless Interceptor & Redirect Sniffer.
Navigates through JavaScript-driven countdowns and intercepts final destination URLs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from urllib.parse import urlparse

from ripper.universal_bypasser.models import BypassContext, GateType, ShortlinkResult


class PlaywrightInterceptor:
    """Uses Playwright headless browser to intercept complex ad-gates."""

    def __init__(self, context: Optional[BypassContext] = None):
        self.context = context or BypassContext()

    async def solve(self, url: str) -> ShortlinkResult:
        start_time = time.time()
        intermediates = [url]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ShortlinkResult(
                original_url=url,
                resolved_url=None,
                gate_type=GateType.CLOUD_GATE,
                success=False,
                duration=time.time() - start_time,
                solver_used="playwright_interceptor",
                error="Playwright is not installed in the current environment"
            )

        try:
            async with async_playwright() as p:
                browser = None
                browser_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

                # 1. Try system Google Chrome or Microsoft Edge
                for ch in ("chrome", "msedge"):
                    try:
                        browser = await p.chromium.launch(channel=ch, headless=True, args=browser_args)
                        break
                    except Exception:
                        continue

                # 2. Try Camoufox anti-detect binary if available
                if browser is None:
                    try:
                        from ripper.browser_bypass import find_camoufox_executable
                        fox_bin = find_camoufox_executable()
                        if fox_bin:
                            browser = await p.firefox.launch(executable_path=fox_bin, headless=True)
                    except Exception:
                        pass

                # 3. Fallback to default Playwright chromium
                if browser is None:
                    browser = await p.chromium.launch(headless=True, args=browser_args)

                # Use no_viewport if firefox/camoufox to prevent protocol crash
                is_firefox = getattr(browser, "_browser_type", None) and getattr(browser._browser_type, "name", "") == "firefox"
                if is_firefox:
                    context = await browser.new_context(user_agent=self.context.user_agent, no_viewport=True)
                    page = await context.new_page()
                else:
                    page = await browser.new_page(
                        user_agent=self.context.user_agent,
                        viewport={"width": 1280, "height": 720}
                    )

                found_target: Optional[str] = None
                orig_domain = urlparse(url).netloc

                # Intercept network requests / responses
                def on_request(req):
                    nonlocal found_target
                    req_url = req.url
                    parsed_req = urlparse(req_url)
                    if parsed_req.netloc and parsed_req.netloc != orig_domain:
                        if not req_url.endswith((".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico")):
                            if any(ext in req_url for ext in ["streamtape", "dood", "mixdrop", "drive.google", "mega.nz"]):
                                found_target = req_url

                page.on("request", on_request)

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    intermediates.append(page.url)

                    # Poll for redirects
                    for _ in range(10):
                        if found_target:
                            break
                        cur_url = page.url
                        if cur_url != url and urlparse(cur_url).netloc != orig_domain:
                            found_target = cur_url
                            break
                        await asyncio.sleep(0.5)

                    if not found_target and page.url != url:
                        if urlparse(page.url).netloc != orig_domain:
                            found_target = page.url

                finally:
                    await browser.close()

                if found_target:
                    intermediates.append(found_target)
                    return ShortlinkResult(
                        original_url=url,
                        resolved_url=found_target,
                        gate_type=GateType.CLOUD_GATE,
                        success=True,
                        duration=time.time() - start_time,
                        solver_used="playwright_interceptor",
                        intermediate_urls=intermediates
                    )

        except Exception as e:
            return ShortlinkResult(
                original_url=url,
                resolved_url=None,
                gate_type=GateType.CLOUD_GATE,
                success=False,
                duration=time.time() - start_time,
                solver_used="playwright_interceptor",
                intermediate_urls=intermediates,
                error=str(e)
            )

        return ShortlinkResult(
            original_url=url,
            resolved_url=None,
            gate_type=GateType.CLOUD_GATE,
            success=False,
            duration=time.time() - start_time,
            solver_used="playwright_interceptor",
            intermediate_urls=intermediates,
            error="Playwright interceptor did not detect outbound destination"
        )
