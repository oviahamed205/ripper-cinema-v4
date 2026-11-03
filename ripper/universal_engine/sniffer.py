"""
ripper.universal_engine.sniffer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dynamic headless browser engine with real-time socket-level packet sniffing
and automated gate-clicking.
Inspired by Playwright network interception and Crawl4AI dynamic click execution.
Captures live direct streams (.mp4, .mkv, .m3u8, .mpd) and signed CDN tokens
even when obfuscated behind JavaScript countdown timers or anti-bot protections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..media import MediaDownloadItem, ServerMirror
from .heuristics import SemanticHeuristicExtractor

logger = logging.getLogger("ripper.universal_engine.sniffer")

# Video & Stream Content Types
VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/webm",
    "video/x-matroska",
    "video/quicktime",
    "video/x-msvideo",
    "application/x-mpegurl",
    "application/vnd.apple.mpegurl",
    "application/dash+xml",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".m3u8", ".mpd", ".ts", ".m4s",
}

# Auto-Clicker Target Patterns
CLICK_TARGET_REGEX = re.compile(
    r"(?:get\s*link|generate\s*link|download\s*now|direct\s*download|"
    r"fast\s*download|click\s*here\s*to\s*verify|proceed|download)",
    re.I,
)


class HeadlessStreamSniffer:
    """
    Spawns an evasive stealth browser instance, listens to all network traffic,
    automatically triggers download gates/countdowns, and extracts active video streams.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: float = 12.0,
        wait_after_load: float = 3.0,
    ):
        self.headless = headless
        self.timeout = timeout
        self.wait_after_load = wait_after_load
        self.heuristic_extractor = SemanticHeuristicExtractor()

    async def is_playwright_available(self) -> bool:
        """Verifies whether Playwright and browser drivers are installed."""
        try:
            import playwright.async_api
            return True
        except ImportError:
            return False

    async def sniff_and_extract(self, url: str) -> List[MediaDownloadItem]:
        """
        Executes dynamic navigation, captures real-time video streams from network packets,
        clicks through intermediate countdown gates, and returns unified MediaDownloadItems.
        """
        if not await self.is_playwright_available():
            logger.warning("[Sniffer] Playwright not installed. Skipping headless browser tier.")
            return []

        from playwright.async_api import async_playwright

        sniffed_streams: List[Tuple[str, str]] = []  # (stream_url, mime_type)
        captured_api_links: Set[str] = set()
        hydrated_html = ""

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-infobars",
                        "--disable-dev-shm-usage",
                    ],
                )

                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/128.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                    is_mobile=False,
                    has_touch=False,
                    locale="en-US",
                    timezone_id="America/New_York",
                )

                # Stealth evasion scripts
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                """)

                page = await context.new_page()

                # 1. Packet Interception Listener
                async def handle_response(response):
                    try:
                        resp_url = response.url
                        headers = response.headers
                        content_type = headers.get("content-type", "").lower().split(";")[0].strip()

                        # Detect video streams by MIME type
                        if content_type in VIDEO_MIME_TYPES:
                            sniffed_streams.append((resp_url, content_type))
                            logger.info(f"[Sniffer] Intercepted stream MIME: {resp_url[:70]}")
                            return

                        # Detect video streams by file extension
                        parsed_path = urlparse(resp_url).path.lower()
                        if any(parsed_path.endswith(ext) for ext in VIDEO_EXTENSIONS):
                            sniffed_streams.append((resp_url, content_type or "video/mp4"))
                            logger.info(f"[Sniffer] Intercepted stream ext: {resp_url[:70]}")
                            return

                        # Detect API payloads returning JSON download objects
                        if "application/json" in content_type or "/api/" in resp_url:
                            try:
                                json_data = await response.json()
                                self._scan_json_for_media_urls(json_data, captured_api_links)
                            except Exception:
                                pass
                    except Exception:
                        pass

                page.on("response", handle_response)

                # 2. Navigate to target URL
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                except Exception as e:
                    logger.warning(f"[Sniffer] Initial page navigation error: {e}")

                # Wait for initial JS hydration
                await asyncio.sleep(self.wait_after_load)

                # 3. Autonomous Gate & Button Clicker
                await self._attempt_auto_click(page)

                # Wait for post-click countdowns & network streams
                await asyncio.sleep(2.0)

                # 4. Harvest Fully Hydrated DOM
                hydrated_html = await page.content()
                await context.close()
                await browser.close()

        except Exception as e:
            logger.error(f"[Sniffer] Headless execution failed: {e}", exc_info=True)

        # 5. Synthesize Results
        results: List[MediaDownloadItem] = []

        # Convert Sniffed Network Streams into Media Items
        for stream_url, mime in sniffed_streams:
            is_hls = ".m3u8" in stream_url.lower() or "mpegurl" in mime
            quality = "1080P Direct Stream" if not is_hls else "HLS Adaptive Stream"
            item = MediaDownloadItem(
                title=f"LIVE STREAM [{mime}]",
                movie_name="Stream Capture",
                quality="1080P" if not is_hls else "Adaptive",
                codec="H.264",
                size_str="Live Stream",
                audio_info="Original",
                short_link=stream_url,
                unshortened_landing_url=stream_url,
                servers=[
                    ServerMirror(
                        server_type="Direct Stream Sniffer",
                        stream_url=stream_url,
                        direct_download_url=stream_url if not is_hls else None,
                        status="Live",
                    )
                ],
            )
            results.append(item)

        # Parse the Fully Hydrated DOM with Heuristic Extractor
        if hydrated_html:
            dom_items = self.heuristic_extractor.extract_items(hydrated_html, base_url=url)
            results.extend(dom_items)

        # Add any API discovered links
        for api_url in captured_api_links:
            if not any(it.short_link == api_url for it in results):
                results.append(
                    MediaDownloadItem(
                        title="API Discovered Stream",
                        movie_name="Extracted Media",
                        quality="1080P",
                        codec="HEVC",
                        size_str="Auto",
                        audio_info="Original",
                        short_link=api_url,
                        unshortened_landing_url=api_url,
                    )
                )

        return results

    async def _attempt_auto_click(self, page) -> None:
        """
        Locates interactive elements matching 'Get Link' or 'Download' and clicks them
        to trigger stream generation or bypass countdowns.
        """
        try:
            # Locate candidate buttons / anchors by text
            elements = await page.query_selector_all("button, a, input[type='submit']")
            for el in elements:
                try:
                    text = (await el.inner_text() or "").strip()
                    if CLICK_TARGET_REGEX.search(text):
                        is_visible = await el.is_visible()
                        if is_visible:
                            logger.info(f"[Sniffer] Clicking interactive gate button: '{text}'")
                            await el.click(timeout=2000)
                            await asyncio.sleep(1.5)
                            break
                except Exception:
                    continue
        except Exception:
            pass

    def _scan_json_for_media_urls(self, data, link_set: Set[str]) -> None:
        """Recursively scans parsed JSON response bodies for direct download/stream URLs."""
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str):
                    if any(ext in v.lower() for ext in VIDEO_EXTENSIONS) or "drive" in v.lower():
                        if v.startswith("http"):
                            link_set.add(v)
                else:
                    self._scan_json_for_media_urls(v, link_set)
        elif isinstance(data, list):
            for item in data:
                self._scan_json_for_media_urls(item, link_set)
