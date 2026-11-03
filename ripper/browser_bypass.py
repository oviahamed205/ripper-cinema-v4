"""
Headless Camoufox & Playwright Cloudflare Turnstile Bypass Module for unshorten-cli.

Enables automated headless bypass of Cloudflare Turnstile, DDoS-Guard, and
anti-bot verification walls. Discovers Camoufox on Windows, Linux, and macOS
(or via CAMOUFOX_PATH / UNSHORTEN_CAMOUFOX_PATH).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

CAMOUFOX_DEFAULT_PATHS = [
    r"D:\camoufox-152.0.4-beta.28-win.i686\camoufox.exe",
    r"C:\camoufox\camoufox.exe",
    os.path.expanduser(r"~\camoufox\camoufox.exe"),
    os.path.expanduser("~/camoufox/camoufox"),
    os.path.expanduser("~/camoufox/camoufox.exe"),
    "/opt/camoufox/camoufox",
    "/usr/local/bin/camoufox",
    "/usr/bin/camoufox",
    r"C:\Program Files\Camoufox\camoufox.exe",
    r"C:\Program Files (x86)\Camoufox\camoufox.exe",
]

_CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "checking your browser",
    "ddos-guard",
    "please wait",
    "verify you are human",
)

_SAFE_CLICK_SELECTORS = (
    "button.visit-btn",
    "a.btn-download",
    "a.dlbtn",
    "button#challenge-stage",
    "input[type='submit']",
    "button[type='submit']",
)

_BROWSER_LOCK = asyncio.Lock()
_CLEARANCE_COOKIE_CACHE: dict[str, list[dict]] = {}

try:
    from .resolver.core.honeypot_filter import is_honeypot_url
except ImportError:
    def is_honeypot_url(url: str) -> bool:
        traps = ["vglist.cv", "vegamovies-apk.com", "adsterra", "apk-download", "bestdeal", "clickadu"]
        return any(t in url.lower() for t in traps)


def _env_path(name: str) -> Optional[str]:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    return str(raw).strip().strip('"')


def _looks_like_camoufox_binary(path: str) -> bool:
    """True when path exists and looks like a Camoufox/Firefox executable."""
    if not path:
        return False
    try:
        candidate = Path(path)
        if not candidate.is_file():
            return False
        lowered = candidate.name.lower()
        return lowered.startswith("camoufox") or lowered in {"firefox", "firefox.exe"}
    except Exception:
        return False


def _iter_camoufox_candidates() -> List[str]:
    """Build an ordered list of possible Camoufox executable locations."""
    found: List[str] = []
    seen = set()

    def _add(raw: Optional[str]) -> None:
        if not raw:
            return
        expanded = os.path.expandvars(os.path.expanduser(str(raw)))
        if expanded in seen:
            return
        seen.add(expanded)
        found.append(expanded)

    _add(_env_path("UNSHORTEN_CAMOUFOX_PATH"))
    _add(_env_path("CAMOUFOX_PATH"))

    for default in CAMOUFOX_DEFAULT_PATHS:
        _add(default)

    for bin_name in ("camoufox", "camoufox.exe", "camoufox-bin"):
        _add(shutil.which(bin_name))

    glob_roots = [Path.home(), Path.cwd()]
    for drive in ("C:\\", "D:\\"):
        if Path(drive).exists():
            glob_roots.append(Path(drive))

    for root in glob_roots:
        try:
            for match in root.glob("camoufox*/camoufox.exe"):
                _add(str(match))
            for match in root.glob("camoufox*/camoufox"):
                _add(str(match))
        except Exception:
            continue

    return found


def find_camoufox_executable() -> Optional[str]:
    """Find installed Camoufox anti-detect browser binary."""
    for path in _iter_camoufox_candidates():
        if _looks_like_camoufox_binary(path):
            return path
    return None


def _html_still_challenged(title: str, url: str, html_body: str) -> bool:
    """True when the page still looks like a bot-challenge wall."""
    title_l = (title or "").lower()
    url_l = (url or "").lower()
    body_l = (html_body or "").lower()
    if any(marker in title_l for marker in _CHALLENGE_TITLE_MARKERS):
        return True
    if "__cf_chl" in url_l or "challenges.cloudflare.com" in url_l:
        return True
    if "just a moment..." in body_l and ("cloudflare" in body_l or "/cdn-cgi/" in body_l):
        return True
    if "cf-turnstile" in body_l or "_cf_chl_opt" in body_l:
        return True
    if "ddos-guard" in body_l and "checking your browser" in body_l:
        return True
    return False


async def _cookie_cleared(context: object) -> bool:
    """True when the browser context holds a cf_clearance cookie."""
    try:
        cookies = await context.cookies()  # type: ignore[union-attr]
    except Exception:
        return False
    for cookie in cookies or []:
        try:
            if str(cookie.get("name", "")).lower() == "cf_clearance" and cookie.get("value"):
                return True
        except Exception:
            continue
    return False


async def _safe_click_continue(page: object) -> None:
    """Click a post-challenge continue/generate button, never a 'please wait' control or honeypot."""
    import re
    # 1. Fast path with known selectors
    for selector in _SAFE_CLICK_SELECTORS:
        try:
            button = await page.query_selector(selector)  # type: ignore[union-attr]
            if not button:
                continue
            label = ""
            try:
                label = (await button.inner_text() or "").strip().lower()
            except Exception:
                label = ""
            if any(bad in label for bad in ("please wait", "loading", "checking", "just a moment", "install", "apk")):
                continue
            href = ""
            try:
                href = (await button.get_attribute("href") or "").strip()
            except Exception:
                href = ""
            if href and is_honeypot_url(href):
                continue

            await button.click(timeout=2500)
            await asyncio.sleep(1.5)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            continue

    # 2. Semantic accessibility & text matching fallback
    try:
        candidates = await page.query_selector_all("button, a, input[type='button'], input[type='submit'], div[role='button']")  # type: ignore[union-attr]
        positive_pattern = re.compile(r"(?:proceed|get\s*link|generate\s*link|continue|download|verify|visit|click\s*here)", re.I)
        for btn in (candidates or [])[:20]:
            try:
                text = (await btn.inner_text() or "").strip().lower()
                val = (await btn.get_attribute("value") or "").strip().lower()
                combined_text = f"{text} {val}".strip()
                if any(bad in combined_text for bad in ("please wait", "loading", "checking", "just a moment", "install", "apk", "betting", "casino")):
                    continue

                href = (await btn.get_attribute("href") or "").strip()
                if href and is_honeypot_url(href):
                    continue

                if positive_pattern.search(combined_text):
                    await btn.click(timeout=2500)
                    await asyncio.sleep(1.5)
                    return
            except Exception:
                continue
    except Exception:
        pass


async def _read_page_state(page: object) -> Tuple[str, str, str]:
    """Return (url, title, html) from a Playwright/Camoufox page."""
    current_url = ""
    title = ""
    html_body = ""
    try:
        current_url = str(getattr(page, "url", "") or "")
    except Exception:
        current_url = ""
    try:
        title = await page.title()  # type: ignore[union-attr]
    except Exception:
        title = ""
    try:
        html_body = await page.content()  # type: ignore[union-attr]
    except Exception:
        html_body = ""
    return current_url, title or "", html_body or ""


async def _wait_for_clearance(page: object, context: object, deadline: float) -> None:
    """Poll until the challenge disappears, a clearance cookie appears, or time runs out."""
    while time_remaining(deadline) > 0:
        current_url, title, html_body = await _read_page_state(page)
        if await _cookie_cleared(context) and not _html_still_challenged(title, current_url, html_body):
            return
        if current_url and not _html_still_challenged(title, current_url, html_body):
            return
        await asyncio.sleep(min(1.0, max(0.1, time_remaining(deadline))))


def time_remaining(deadline: float) -> float:
    """Seconds left before an absolute deadline."""
    return max(0.0, deadline - time.monotonic())


async def _run_camoufox_package(url: str, executable: str, timeout: float) -> Tuple[bool, str, str]:
    """Drive the official Camoufox Python API if it is installed."""
    try:
        from camoufox.async_api import AsyncCamoufox
    except Exception:
        return False, url, ""

    deadline = time.monotonic() + timeout
    browser = None
    try:
        async with AsyncCamoufox(
            headless=True,
            executable_path=executable,
        ) as browser:
            page = await asyncio.wait_for(browser.new_page(), timeout=min(15.0, timeout))
            context = page.context
            domain = urlparse(url).netloc.lower()
            if domain in _CLEARANCE_COOKIE_CACHE:
                try:
                    await context.add_cookies(_CLEARANCE_COOKIE_CACHE[domain])
                except Exception:
                    pass

            remaining_ms = int(time_remaining(deadline) * 1000)
            if remaining_ms <= 0:
                return False, url, ""
            try:
                await page.goto(url, timeout=remaining_ms, wait_until="domcontentloaded")
            except asyncio.CancelledError:
                raise
            except Exception:
                if time_remaining(deadline) <= 0:
                    return False, url, ""
            await _wait_for_clearance(page, context, deadline)
            if time_remaining(deadline) > 2:
                await _safe_click_continue(page)
                await _wait_for_clearance(page, context, deadline)
            final_url, title, html_body = await _read_page_state(page)
            cleared = (not _html_still_challenged(title, final_url, html_body)) or await _cookie_cleared(context)
            if cleared:
                try:
                    all_cookies = await context.cookies()
                    if all_cookies:
                        _CLEARANCE_COOKIE_CACHE[domain] = all_cookies
                except Exception:
                    pass
            return bool(cleared and (final_url or html_body)), final_url or url, html_body
    except asyncio.CancelledError:
        raise
    except Exception:
        return False, url, ""


async def _run_playwright_firefox(url: str, executable: str, timeout: float) -> Tuple[bool, str, str]:
    """Fallback: launch Camoufox through Playwright's Firefox engine."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False, url, ""

    deadline = time.monotonic() + timeout
    playwright = None
    browser = None
    context = None
    try:
        playwright = await async_playwright().start()
        browser = await asyncio.wait_for(
            playwright.firefox.launch(executable_path=executable, headless=True),
            timeout=min(20.0, timeout),
        )
        context = await browser.new_context(
            no_viewport=True,
            locale="en-US",
        )
        page = await context.new_page()
        remaining_ms = int(time_remaining(deadline) * 1000)
        if remaining_ms <= 0:
            return False, url, ""
        try:
            await page.goto(url, timeout=remaining_ms, wait_until="domcontentloaded")
        except asyncio.CancelledError:
            raise
        except Exception:
            if time_remaining(deadline) <= 0:
                return False, url, ""
        await _wait_for_clearance(page, context, deadline)
        if time_remaining(deadline) > 2:
            await _safe_click_continue(page)
            await _wait_for_clearance(page, context, deadline)
        final_url, title, html_body = await _read_page_state(page)
        cleared = (not _html_still_challenged(title, final_url, html_body)) or await _cookie_cleared(context)
        return bool(cleared and (final_url or html_body)), final_url or url, html_body
    except asyncio.CancelledError:
        raise
    except Exception:
        return False, url, ""
    finally:
        for closer in (context, browser):
            if closer is None:
                continue
            try:
                await closer.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass


async def _run_playwright_chromium(url: str, timeout: float) -> Tuple[bool, str, str]:
    """Fallback: launch system Google Chrome or Microsoft Edge through Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False, url, ""

    deadline = time.monotonic() + timeout
    playwright = None
    browser = None
    context = None
    try:
        playwright = await async_playwright().start()
        for ch in ("chrome", "msedge"):
            try:
                browser = await asyncio.wait_for(
                    playwright.chromium.launch(channel=ch, headless=True),
                    timeout=min(15.0, timeout),
                )
                break
            except Exception:
                continue

        if browser is None:
            return False, url, ""

        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = await context.new_page()
        remaining_ms = int(time_remaining(deadline) * 1000)
        if remaining_ms <= 0:
            return False, url, ""
        try:
            await page.goto(url, timeout=remaining_ms, wait_until="domcontentloaded")
        except asyncio.CancelledError:
            raise
        except Exception:
            if time_remaining(deadline) <= 0:
                return False, url, ""
        await _wait_for_clearance(page, context, deadline)
        if time_remaining(deadline) > 2:
            await _safe_click_continue(page)
            await _wait_for_clearance(page, context, deadline)
        final_url, title, html_body = await _read_page_state(page)
        cleared = (not _html_still_challenged(title, final_url, html_body)) or await _cookie_cleared(context)
        return bool(cleared and (final_url or html_body)), final_url or url, html_body
    except asyncio.CancelledError:
        raise
    except Exception:
        return False, url, ""
    finally:
        for closer in (context, browser):
            if closer is None:
                continue
            try:
                await closer.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass


async def resolve_with_browser_bypass(url: str, timeout: float = 30.0) -> Tuple[bool, str, str]:
    """
    Launch headless Camoufox (or Google Chrome / Edge), navigate to a challenge URL,
    wait for Turnstile clearance, and return (success, final_url, html_content).

    Returns (False, url, "") when browsers are missing, the challenge
    is still up, or the browser times out. Never leaves a browser process running.
    """
    if not url or not str(url).strip():
        return False, url or "", ""

    camoufox_exe = find_camoufox_executable()

    try:
        timeout_s = float(timeout)
    except (TypeError, ValueError):
        timeout_s = 30.0
    timeout_s = max(5.0, min(timeout_s, 120.0))

    async with _BROWSER_LOCK:
        try:
            if camoufox_exe:
                ok, final_url, html_body = await asyncio.wait_for(
                    _run_camoufox_package(url, camoufox_exe, timeout_s),
                    timeout=timeout_s + 5.0,
                )
                if ok:
                    return True, final_url, html_body
                ok, final_url, html_body = await asyncio.wait_for(
                    _run_playwright_firefox(url, camoufox_exe, timeout_s),
                    timeout=timeout_s + 5.0,
                )
                if ok:
                    return True, final_url, html_body

            # Fallback to system Google Chrome / Microsoft Edge
            ok, final_url, html_body = await asyncio.wait_for(
                _run_playwright_chromium(url, timeout_s),
                timeout=timeout_s + 5.0,
            )
            return ok, final_url, html_body
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            return False, url, ""
        except Exception:
            return False, url, ""
