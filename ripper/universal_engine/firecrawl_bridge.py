"""
ripper.universal_engine.firecrawl_bridge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cloud-based dynamic scraping bridge utilizing the Firecrawl API.
When local headless browsers fail due to residential IP bans, CAPTCHAs,
or restricted environments, Firecrawl executes the page remotely and delivers
clean, fully hydrated HTML and markdown for semantic extraction.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional
import httpx

from ..media import MediaDownloadItem
from .heuristics import SemanticHeuristicExtractor

logger = logging.getLogger("ripper.universal_engine.firecrawl")

DEFAULT_FIRECRAWL_KEY = "fc-1a1447d5a89441fabcc45c9eeee4b45c"
FIRECRAWL_SCRAPE_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

MD_LINK_REGEX = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


class FirecrawlCloudBridge:
    """
    Interfaces with Firecrawl v2 API to retrieve cloud-rendered HTML and markdown,
    bypassing Cloudflare Turnstile, anti-scraping protections, and complex client SPAs.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        self.api_key = api_key or os.environ.get("FIRECRAWL_API_KEY", DEFAULT_FIRECRAWL_KEY)
        self.timeout = timeout
        self.heuristic_extractor = SemanticHeuristicExtractor()

    async def scrape_and_extract(
        self,
        url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[MediaDownloadItem]:
        """
        Submits the URL to Firecrawl's cloud cluster, retrieves the rendered DOM/markdown,
        and parses it into structured MediaDownloadItems.
        """
        if not self.api_key:
            logger.warning("[Firecrawl] No API key provided or found in environment.")
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "url": url,
            "formats": ["html", "markdown"],
            "waitFor": 3000,
            "onlyMainContent": False,
        }

        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close_client = True

        try:
            logger.info(f"[Firecrawl] Dispatching cloud scrape request for: {url[:60]}")
            resp = await client.post(FIRECRAWL_SCRAPE_ENDPOINT, json=payload, headers=headers)
            
            if resp.status_code != 200:
                logger.warning(f"[Firecrawl] API returned HTTP {resp.status_code}: {resp.text[:120]}")
                return []

            data = resp.json()
            if not data.get("success"):
                logger.warning(f"[Firecrawl] Scrape unsuccessful: {data.get('error')}")
                return []

            scrape_data = data.get("data", {})
            html_content = scrape_data.get("html", "")
            markdown_content = scrape_data.get("markdown", "")

            results: List[MediaDownloadItem] = []

            # 1. Parse Rendered HTML via Heuristic Extractor
            if html_content:
                dom_items = self.heuristic_extractor.extract_items(html_content, base_url=url)
                results.extend(dom_items)

            # 2. Parse Markdown Links if DOM extraction had 0 results
            if not results and markdown_content:
                md_items = self._parse_markdown_links(markdown_content, url)
                results.extend(md_items)

            logger.info(f"[Firecrawl] Successfully extracted {len(results)} items via cloud scrape.")
            return results

        except Exception as e:
            logger.error(f"[Firecrawl] Cloud scrape failed: {e}", exc_info=True)
            return []
        finally:
            if should_close_client:
                await client.aclose()

    def _parse_markdown_links(self, markdown: str, base_url: str) -> List[MediaDownloadItem]:
        """Extracts media download candidates from markdown [Label](URL) formatting."""
        items: List[MediaDownloadItem] = []
        for match in MD_LINK_REGEX.finditer(markdown):
            label, link = match.group(1).strip(), match.group(2).strip()
            score, meta = self.heuristic_extractor.score_text_for_media(label)
            if score >= 0.35 or meta["quality"] or meta["size_str"]:
                quality = meta["quality"] or "720P"
                codec = meta["codec"] or "X264"
                size = meta["size_str"] or "N/A"
                title = f"{codec} {quality}" + (f" [{size}]" if size != "N/A" else "")
                items.append(
                    MediaDownloadItem(
                        title=title,
                        movie_name="Cloud Extracted Media",
                        quality=quality,
                        codec=codec,
                        size_str=size,
                        audio_info=meta["audio"] or "Dual Audio",
                        short_link=link,
                        unshortened_landing_url=link,
                    )
                )
        return items
