"""
ripper.healer.llm_dom_diagnostics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Zero-shot structural DOM reasoning powered by local GGUF models.
Runs K2-Horizon-1B-BF16 directly against Crawl4AI-pruned semantic DOM trees
to diagnose mutated layouts, extract hidden mirrors, and recover links.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

from ..media import MediaDownloadItem, ServerMirror
from .anomaly_detector import AnomalyDetector
from .dom_pruner import DOMPruner
from .models import HealerConfig

logger = logging.getLogger("ripper.healer.llm_dom_diagnostics")

SYSTEM_PROMPT = """You are an expert autonomous web scraper analyzing a mutated media download webpage.
Extract all valid movie/episode download links from the provided structural outline.
Exclude all ads, betting, casino, apk, and honeypot traps.

Return ONLY a JSON array of objects with the following schema:
[
  {
    "movie_name": "Full title of the movie or episode",
    "quality": "480p / 720p / 1080p / 2160p / 4K",
    "size_str": "File size if mentioned (e.g. 1.4GB) or unknown",
    "url": "https://...",
    "server_name": "Server name (e.g. FastDL, HubCloud, GDrive, PixelDrain)"
  }
]
"""


class LLMDiagnostics:
    """
    Executes local GGUF or Cloud LLM inference over pruned DOM structures.
    """

    def __init__(self, config: Optional[HealerConfig] = None):
        self.config = config or HealerConfig()
        self.pruner = DOMPruner(max_bytes=self.config.max_pruned_dom_bytes)
        self.detector = AnomalyDetector()
        self._llama_model = None

    def _get_llama_model(self):
        """Lazily loads local GGUF model via llama_cpp if available and file exists."""
        if self._llama_model is not None:
            return self._llama_model

        model_path = self.config.local_model_path
        if not model_path or not os.path.isfile(model_path):
            return None

        try:
            from llama_cpp import Llama
            logger.info(f"[LLMDiagnostics] Initializing local GGUF: {model_path}")
            self._llama_model = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=os.cpu_count() or 4,
                verbose=False,
            )
            return self._llama_model
        except Exception as e:
            logger.debug(f"[LLMDiagnostics] Local Llama initialization skipped: {e}")
            return None

    async def diagnose_and_extract(
        self,
        html: str,
        url: str,
        client: Optional[httpx.AsyncClient] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[MediaDownloadItem]:
        """
        Compresses HTML into a dense token tree, runs inference, and parses structured items.
        """
        if not html:
            return []

        # 1. Prune the DOM tree
        if progress_callback:
            progress_callback("🧹 [LLM] Pruning DOM to semantic token outline...")
        pruned_dom = self.pruner.prune(html, base_url=url)
        if not pruned_dom:
            return []

        prompt_user = f"Target URL: {url}\n\nStructural Page Content:\n{pruned_dom}\n\nExtract JSON array:"
        raw_output = ""

        # 2. Try Local GGUF Engine
        llama = self._get_llama_model()
        if llama:
            if progress_callback:
                progress_callback("🧠 [LLM] Running local K2-Horizon GGUF inference...")
            try:
                response = llama.create_chat_completion(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt_user},
                    ],
                    max_tokens=512,
                    temperature=0.1,
                )
                raw_output = response["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"[LLMDiagnostics] Local inference failed: {e}")

        # 3. Fallback to Cloud LLM (OpenAI) if configured
        if not raw_output and os.environ.get("OPENAI_API_KEY"):
            if progress_callback:
                progress_callback("☁️ [LLM] Fallback to Cloud LLM extractor...")
            try:
                api_key = os.environ["OPENAI_API_KEY"]
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt_user},
                    ],
                    "temperature": 0.1,
                }
                async with httpx.AsyncClient(timeout=self.config.timeout_llm) as http:
                    r = await http.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                    if r.status_code == 200:
                        raw_output = r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"[LLMDiagnostics] Cloud LLM fallback failed: {e}")

        # 4. Fallback to Regex Heuristic parsing of the pruned DOM directly
        if not raw_output:
            logger.debug("[LLMDiagnostics] Parsing pruned DOM via fallback parser.")
            return self._heuristic_fallback(pruned_dom, url)

        # 5. Parse JSON
        return self._parse_json_items(raw_output, url)

    def _parse_json_items(self, raw_json_text: str, base_url: str) -> List[MediaDownloadItem]:
        """Defensively parses model output into validated MediaDownloadItems."""
        items: List[MediaDownloadItem] = []
        try:
            # Extract JSON block (greedy match from first [ to last ])
            json_match = re.search(r"\[\s*\{.*\}\s*\]", raw_json_text, re.DOTALL)
            if not json_match:
                return []

            data = json.loads(json_match.group(0))
            for entry in data:
                href = entry.get("url", "").strip()
                if not href or not href.startswith("http"):
                    continue

                movie_name = entry.get("movie_name", "Recovered Media")
                quality = entry.get("quality", "1080p Web-DL")
                size_str = entry.get("size_str", "Unknown")
                server_name = entry.get("server_name", "Cloud Mirror")

                item = MediaDownloadItem(
                    title=f"{movie_name} [{quality}]",
                    movie_name=movie_name,
                    quality=quality,
                    codec="WEB-DL",
                    size_str=size_str,
                    audio_info="",
                    short_link=href,
                    unshortened_landing_url=href,
                    servers=[ServerMirror(label=server_name, intermediate_url=href, direct_download_url=href)],
                )
                items.append(item)

        except Exception as e:
            logger.debug(f"[LLMDiagnostics] JSON parse error: {e}")

        return self.detector.filter_safe_items(items)

    def _heuristic_fallback(self, pruned_text: str, base_url: str) -> List[MediaDownloadItem]:
        """Extracts media links directly from pruned token outline when no LLM is present."""
        items: List[MediaDownloadItem] = []
        lines = pruned_text.splitlines()
        current_title = "Recovered Movie"

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("[H") and "]" in line_str:
                current_title = line_str.split("]", 1)[1].strip()
            elif line_str.startswith("LINK:"):
                # Format: LINK: Label -> href
                match = re.search(r"LINK:\s*(.+?)\s*->\s*(https?://\S+)", line_str)
                if match:
                    label, href = match.group(1).strip(), match.group(2).strip()

                    # Extract quality from label or URL
                    quality = "1080P"
                    for q in ["2160p", "4k", "1080p", "720p", "480p"]:
                        if q in label.lower() or q in href.lower():
                            quality = q.upper()
                            break

                    server = "Direct Mirror"
                    for s in ["FastDL", "HubCloud", "GDrive", "PixelDrain", "VCloud", "Filepress"]:
                        if s.lower() in label.lower() or s.lower() in href.lower():
                            server = s
                            break

                    item = MediaDownloadItem(
                        title=f"{current_title} [{quality}]",
                        movie_name=current_title,
                        quality=quality,
                        codec="WEB-DL",
                        size_str="Auto-Healed",
                        audio_info="",
                        short_link=href,
                        unshortened_landing_url=href,
                        servers=[ServerMirror(label=server, intermediate_url=href, direct_download_url=href)],
                    )
                    items.append(item)

        return self.detector.filter_safe_items(items)
