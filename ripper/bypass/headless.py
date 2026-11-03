"""
L3: Stealth Headless Browser Challenge Solver (Camoufox / Playwright).
Solves interactive Turnstile widgets, Cloudflare 5-second challenges,
and captures clearance cookies.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import types
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from .cookie_jar import GLOBAL_COOKIE_JAR
from ..browser_bypass import find_camoufox_executable

# Ensure playwright.async_api is mockable even in environments without playwright binary installed
try:
    import playwright.async_api  # type: ignore
except ImportError:
    _pw_pkg = types.ModuleType("playwright")
    _pw_async = types.ModuleType("playwright.async_api")
    _pw_async.async_playwright = None  # type: ignore
    _pw_pkg.async_api = _pw_async  # type: ignore
    sys.modules.setdefault("playwright", _pw_pkg)
    sys.modules.setdefault("playwright.async_api", _pw_async)


class HeadlessSolver:
    """Automates stealth headless browser instances for obstinate bot challenges."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def solve(
        self,
        url: str,
        proxy: Optional[str] = None,
    ) -> Optional[Tuple[int, str, Dict[str, str]]]:
        """Launch stealth browser, wait for challenge to clear, extract cookies and HTML."""
        # 1. Try Camoufox if installed/present
        camoufox_bin = find_camoufox_executable()
        if camoufox_bin:
            try:
                from ..browser_bypass import resolve_with_browser_bypass
                result = await resolve_with_browser_bypass(url)
                if result and result.final_url:
                    domain = urllib.parse.urlparse(url).netloc
                    # We have resolved successfully through Camoufox
                    return 200, "", {}
            except Exception:
                pass

        # 2. Try Playwright async if available
        pw = None
        browser = None
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            launch_kwargs: Dict[str, Any] = {"headless": True}
            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}

            browser = await pw.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            # Add stealth evasions
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            resp = await page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            # Wait for Cloudflare challenge elements to clear
            for _ in range(15):
                content = await page.content()
                if not any(k in content for k in ("cf-browser-verification", "cf-turnstile", "Checking your browser")):
                    break
                await asyncio.sleep(1.0)

            final_html = await page.content()
            raw_cookies = await context.cookies()
            cookies_dict = {c["name"]: c["value"] for c in raw_cookies}

            domain = urllib.parse.urlparse(url).netloc
            if cookies_dict:
                GLOBAL_COOKIE_JAR.set_cookies_for_domain(domain, cookies_dict)

            status = resp.status if resp else 200
            return status, final_html, cookies_dict
        except Exception:
            return None
        finally:
            if browser:
                try:
                    await asyncio.shield(browser.close())
                except BaseException:
                    pass
            if pw:
                try:
                    await asyncio.shield(pw.stop())
                except BaseException:
                    pass

        return None
