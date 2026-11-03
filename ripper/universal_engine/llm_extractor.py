"""
ripper.universal_engine.llm_extractor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Autonomous LLM-assisted structural DOM parser.
When websites utilize randomized CSS modules, heavily obfuscated structures,
or complex layouts that defeat conventional heuristics, this engine passes
a condensed token tree to an LLM to reliably extract media items and links.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from ..media import MediaDownloadItem

logger = logging.getLogger("ripper.universal_engine.llm")

OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class LLMStructuralExtractor:
    """
    Uses OpenAI models to semantically structure obfuscated webpage data
    into standardized media items.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        use_local: bool = False,
    ):
        if use_local:
            self.api_key = None
        else:
            self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.model = model

    def condense_html(self, html: str, max_chars: int = 15000) -> str:
        """
        Strips scripts, styles, svg, and metadata to reduce token consumption,
        retaining only text, headers, and clickable anchor elements.
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "svg", "noscript", "iframe", "meta", "link"]):
            tag.decompose()

        snippets = []
        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "a", "button", "li", "span"]):
            text = el.get_text(separator=" ").strip()
            href = el.get("href", "")
            if href and text:
                snippets.append(f"LINK: {text} -> {href}")
            elif text and len(text) > 2:
                snippets.append(f"TEXT: {text}")

        condensed = "\n".join(snippets)
        return condensed[:max_chars]

    async def _fallback_local_ai(self, html: str, base_url: str) -> List[MediaDownloadItem]:
        """
        Delegates link extraction to local ripper.ai_engine when cloud LLM is unavailable.
        """
        logger.info("[LLMExtractor] Delegating to local ai_engine...")
        try:
            from ..ai_engine import extract_links_ai
            ai_res = await extract_links_ai(html, base_url)
            results: List[MediaDownloadItem] = []
            for it in ai_res.items:
                title = f"{it.codec} {it.quality}" + (f" [{it.size_str}]" if it.size_str != "N/A" else "")
                results.append(
                    MediaDownloadItem(
                        title=title,
                        movie_name=it.movie_name,
                        quality=it.quality,
                        codec=it.codec,
                        size_str=it.size_str,
                        audio_info=it.audio_info,
                        short_link=it.url,
                        unshortened_landing_url=it.url,
                    )
                )
            return results
        except Exception as e:
            logger.warning(f"[LLMExtractor] Local ai_engine fallback failed: {e}")
            return []

    async def extract_items(
        self,
        html: str,
        base_url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[MediaDownloadItem]:
        """
        Invokes LLM with condensed DOM to extract movie download tiers.
        """
        if not self.api_key:
            return await self._fallback_local_ai(html, base_url)

        condensed_dom = self.condense_html(html)
        if not condensed_dom.strip():
            return []

        prompt = f"""You are a precise media link extractor. Analyze this condensed webpage text from {base_url}.
Find all movie/series download links or streaming mirrors.
For each item, extract:
- quality: 480P, 720P, 1080P, or 2160P
- codec: X264, HEVC, REMUX, or WEB-DL
- size: file size string like 1.4GB, 565MB, etc.
- audio: e.g. Dual Audio, Hindi, English
- url: the target link href
- movie_name: clean movie name

Return ONLY valid JSON in this exact structure:
{{
  "movie_name": "Dragon",
  "items": [
    {{"quality": "480P", "codec": "X264", "size": "565MB", "audio": "Dual Audio", "url": "https://..."}}
  ]
}}
"""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a specialized media extraction assistant. Output strict JSON only."},
                {"role": "user", "content": f"{prompt}\n\nWEBPAGE DATA:\n{condensed_dom}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            should_close = True

        try:
            resp = await client.post(OPENAI_CHAT_ENDPOINT, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[LLMExtractor] OpenAI API error {resp.status_code}: {resp.text[:100]}. Falling back to local ai_engine...")
                return await self._fallback_local_ai(html, base_url)

            data = resp.json()
            raw_json = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw_json)

            movie_name = parsed.get("movie_name", "Extracted Movie")
            raw_items = parsed.get("items", [])

            results: List[MediaDownloadItem] = []
            for it in raw_items:
                url = it.get("url", "").strip()
                if not url or not url.startswith("http"):
                    continue
                q = it.get("quality", "720P").upper()
                codec = it.get("codec", "X264").upper()
                size = it.get("size", "N/A")
                audio = it.get("audio", "Dual Audio")
                title = f"{codec} {q}" + (f" [{size}]" if size != "N/A" else "")

                results.append(
                    MediaDownloadItem(
                        title=title,
                        movie_name=movie_name,
                        quality=q,
                        codec=codec,
                        size_str=size,
                        audio_info=audio,
                        short_link=url,
                        unshortened_landing_url=url,
                    )
                )

            logger.info(f"[LLMExtractor] Extracted {len(results)} items via LLM analysis.")
            return results

        except Exception as e:
            logger.error(f"[LLMExtractor] Execution failed: {e}", exc_info=True)
            return await self._fallback_local_ai(html, base_url)
        finally:
            if should_close:
                await client.aclose()
