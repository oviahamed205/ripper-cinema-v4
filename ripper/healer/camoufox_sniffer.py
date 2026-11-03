"""
ripper.healer.camoufox_sniffer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Anti-detection browser packet sniffer powered by Camoufox.
Bypasses Cloudflare Turnstile, anti-bot fingerprinting, and countdown gates.
Sniffs wire-level video packets (.mp4, .m3u8, .mkv) and 10Gbps CDN storage redirects.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from ..media import MediaDownloadItem, ServerMirror
from .anomaly_detector import AnomalyDetector
from .models import HealerConfig

logger = logging.getLogger("ripper.healer.camoufox_sniffer")

STREAM_MIME_TYPES = {
    "video/mp4",
    "video/webm",
    "video/x-matroska",
    "video/quicktime",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
    "application/dash+xml",
    "application/octet-stream",
}

STREAM_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".m3u8", ".mpd", ".ts", ".m4s",
}

STORAGE_CDN_DOMAINS = [
    "googleusercontent.com",
    "pixeldrain.com/api/file",
    "r2.dev",
    "fastdl",
    "hubcloud",
    "vcloud",
    "drive.google.com/uc",
]

GATE_BUTTON_PATTERNS = [
    re.compile(r"get\s*link|generate\s*link|proceed|verify|fast\s*download", re.I),
    re.compile(r"download\s*now|direct\s*download|continue", re.I),
]


class CamoufoxStreamSniffer:
    """
    Automates an evasive Camoufox (Firefox anti-detect) or Playwright instance
    to capture live streams, bypass Turnstile, and click through download gates.
    """

    def __init__(self, config: Optional[HealerConfig] = None):
        self.config = config or HealerConfig()
        self.detector = AnomalyDetector()

    def _resolve_camoufox_executable(self) -> Optional[str]:
        """Verifies if the configured Camoufox binary is available on disk."""
        candidate = self.config.camoufox_path
        if candidate and os.path.isfile(candidate):
            return candidate
        return None

    async def sniff_and_extract(
        self,
        url: str,
        timeout: Optional[float] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[MediaDownloadItem]:
        """
        Navigates stealthily to the target URL, monitors raw network responses for video
        streams or direct CDN redirects, clicks safe gates if needed, and returns extracted items.
        """
        timeout = timeout or self.config.timeout_camoufox
        captured_streams: List[str] = []
        captured_items: List[MediaDownloadItem] = []
        page_title = "Discovered Media Stream"
        resolved_event = asyncio.Event()

        camoufox_bin = self._resolve_camoufox_executable()
        use_camoufox = False

        if camoufox_bin:
            try:
                import camoufox
                use_camoufox = True
            except ImportError:
                use_camoufox = False

        if progress_callback:
            engine_name = "Camoufox C++ Anti-Detect" if use_camoufox else "Playwright Stealth Engine"
            progress_callback(f"🌐 [Sniffer] Launching {engine_name}...")

        # ---------------------------------------------------------------------
        # Response Interception Handler
        # ---------------------------------------------------------------------
        async def on_response(response):
            try:
                resp_url = response.url
                status = response.status

                # Ignore honeypots / analytics
                if self.detector.check_honeypots([MediaDownloadItem(movie_name="", page_url=resp_url)]):
                    return

                # Check Storage Redirects (301, 302, 307)
                if status in (301, 302, 307):
                    location = response.headers.get("location", "")
                    if location and any(dom in location for dom in STORAGE_CDN_DOMAINS):
                        logger.info(f"[Sniffer] Intercepted storage CDN redirect: {location}")
                        captured_streams.append(location)
                        resolved_event.set()
                        return

                # Check Content-Type & URL Extensions
                content_type = response.headers.get("content-type", "").lower()
                parsed_path = urlparse(resp_url).path.lower()

                is_video_mime = any(m in content_type for m in STREAM_MIME_TYPES)
                is_video_ext = any(parsed_path.endswith(ext) for ext in STREAM_EXTENSIONS)
                is_storage_cdn = any(dom in resp_url for dom in STORAGE_CDN_DOMAINS) and ("download" in resp_url or "file" in resp_url)

                if is_video_mime or is_video_ext or is_storage_cdn:
                    # Filter out small preview audio or trackers
                    content_length = int(response.headers.get("content-length", 0) or 0)
                    if content_length > 0 and content_length < 50000 and "m3u8" not in resp_url:
                        return

                    logger.info(f"[Sniffer] Intercepted stream payload: {resp_url} ({content_type})")
                    if resp_url not in captured_streams:
                        captured_streams.append(resp_url)
                    resolved_event.set()

            except Exception as e:
                logger.debug(f"[Sniffer] Response handler exception: {e}")

        # ---------------------------------------------------------------------
        # Browser Session Execution
        # ---------------------------------------------------------------------
        browser = None
        context = None
        playwright_obj = None

        try:
            if use_camoufox:
                from camoufox.async_api import AsyncCamoufox
                browser_mgr = AsyncCamoufox(
                    headless=self.config.headless,
                    executable_path=camoufox_bin,
                )
                browser = await browser_mgr.__aenter__()
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
                )
            else:
                from playwright.async_api import async_playwright
                playwright_obj = await async_playwright().start()
                browser = await playwright_obj.chromium.launch(
                    headless=self.config.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                )

            page = await context.new_page()
            page.on("response", lambda r: asyncio.create_task(on_response(r)))

            # Navigate to target page
            if progress_callback:
                progress_callback(f"⚡ [Sniffer] Navigating to {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page_title = await page.title() or "Discovered Media Stream"

            # Wait briefly for passive stream loading
            try:
                await asyncio.wait_for(resolved_event.wait(), timeout=3.5)
            except asyncio.TimeoutError:
                pass

            # If no stream captured yet, scan for interactive download gates
            if not captured_streams:
                if progress_callback:
                    progress_callback("🔍 [Sniffer] Scanning interactive gate triggers...")

                buttons = await page.query_selector_all("button, a, input[type='button'], input[type='submit']")
                for btn in buttons[:15]:
                    try:
                        text = (await btn.inner_text() or "").strip()
                        href = (await btn.get_attribute("href") or "").strip()

                        # Prevent honeypot clicks
                        if href and self.detector.check_honeypots([MediaDownloadItem(movie_name="", page_url=href)]):
                            continue

                        # Check if matches proceed / download patterns
                        if any(p.search(text) for p in GATE_BUTTON_PATTERNS) or "download" in (href or "").lower():
                            logger.info(f"[Sniffer] Clicking safe gate trigger: '{text}' -> {href}")
                            await btn.click(timeout=2000)
                            try:
                                await asyncio.wait_for(resolved_event.wait(), timeout=3.0)
                                if captured_streams:
                                    break
                            except asyncio.TimeoutError:
                                pass
                    except Exception:
                        continue

            # Final check of page DOM for fastdl or direct video anchors
            if not captured_streams:
                page_html = await page.content()
                from ..media import extract_media_items_from_html
                items = extract_media_items_from_html(page_html, base_url=url)
                if items:
                    captured_items.extend(items)

        except Exception as e:
            logger.warning(f"[Sniffer] Browser automation warning: {e}")

        finally:
            # Clean up browser resources immediately
            try:
                if context:
                    await context.close()
                if browser:
                    if use_camoufox:
                        await browser_mgr.__aexit__(None, None, None)
                    else:
                        await browser.close()
                if playwright_obj:
                    await playwright_obj.stop()
            except Exception:
                pass

        # ---------------------------------------------------------------------
        # Assemble MediaDownloadItem Results
        # ---------------------------------------------------------------------
        if captured_streams:
            clean_title = re.sub(r"\s*[-|–—]\s*(?:Download|Watch Online|Vegamovies|KatMovieHD).*", "", page_title, flags=re.I).strip() or "Direct Stream Download"
            for stream_url in captured_streams:
                quality_val = "1080p Web-DL" if "1080" in stream_url else "Direct Stream"
                item = MediaDownloadItem(
                    title=f"{clean_title} [{quality_val}]",
                    movie_name=clean_title,
                    quality=quality_val,
                    codec="WEB-DL",
                    size_str="Direct Stream",
                    audio_info="",
                    short_link=stream_url,
                    unshortened_landing_url=stream_url,
                    servers=[ServerMirror(label="Direct CDN Stream", intermediate_url=stream_url, direct_download_url=stream_url)],
                )
                captured_items.append(item)

        return self.detector.filter_safe_items(captured_items)
