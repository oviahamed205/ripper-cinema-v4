"""
Master Input Intent Classifier.
Categorizes arbitrary user inputs into deterministic execution intents.
"""

from __future__ import annotations

import re
import urllib.parse
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .domain_kb import (
    is_known_movie_network,
    is_known_shortener,
    is_direct_cdn,
    is_video_embed_host,
    is_direct_video_file_url,
    extract_root_domain,
)
from .title_parser import parse_query_intent, ParsedQueryIntent


class InputIntent(str, Enum):
    DASHBOARD = "DASHBOARD"                      # Empty input -> Launch interactive CLI menu
    URL_DIRECT_STREAM = "URL_DIRECT_STREAM"      # Direct .mkv/.mp4/.m3u8 from CDN/Workers
    URL_MOVIE_PORTAL = "URL_MOVIE_PORTAL"        # Landing page of VegaMovies, OlaMovies, etc.
    URL_SHORTENER = "URL_SHORTENER"              # Ad-gate / Shortener (OUO, GPlinks, Droplink)
    URL_VIDEO_HOST = "URL_VIDEO_HOST"            # Video player host (StreamWish, FileLions, Dood)
    URL_GENERIC_WEB = "URL_GENERIC_WEB"          # Any other HTTP/HTTPS website
    HTML_SNIPPET = "HTML_SNIPPET"                # Raw HTML container pasted by user
    SEARCH_TV_SERIES = "SEARCH_TV_SERIES"        # TV series query with S01/E02 coordinates
    SEARCH_MOVIE = "SEARCH_MOVIE"                # Standard movie title search
    AI_ASSISTANT = "AI_ASSISTANT"                # Conversational AI question or workflow assistance


@dataclass(frozen=True)
class ClassifiedExecutionPlan:
    raw_input: str
    intent: InputIntent
    normalized_url: Optional[str] = None
    query_specs: Optional[ParsedQueryIntent] = None
    target_site: Optional[str] = None
    confidence_score: int = 100
    ai_plan: Optional[Any] = None


RE_HTML_TAGS = re.compile(r"<\s*(?:div|a|p|span|section|table|button|h[1-6]|ul|li)\b[^>]*>", re.IGNORECASE)
RE_BARE_DOMAIN = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s]*)?$")


def normalize_url(text: str) -> Optional[str]:
    """Ensure protocol is present on valid URLs (e.g. 'vegamovies.ph/abc' -> 'https://vegamovies.ph/abc')."""
    t = text.strip()
    if t.startswith(("http://", "https://")):
        return t
    if RE_BARE_DOMAIN.match(t):
        return f"https://{t}"
    return None


def classify_user_input(raw_input: Optional[str]) -> ClassifiedExecutionPlan:
    """
    Forensically inspects raw user input and outputs the exact execution plan.
    """
    if not raw_input or not raw_input.strip():
        return ClassifiedExecutionPlan(
            raw_input="",
            intent=InputIntent.DASHBOARD,
            confidence_score=100
        )

    text = raw_input.strip()

    # 1. Check for HTML Snippet
    if "<" in text and ">" in text and RE_HTML_TAGS.search(text):
        return ClassifiedExecutionPlan(
            raw_input=text,
            intent=InputIntent.HTML_SNIPPET,
            confidence_score=98
        )

    # 2. Check for URL (direct or bare domain)
    url_cand = normalize_url(text)
    if url_cand:
        parsed = urllib.parse.urlparse(url_cand)
        netloc = parsed.netloc.lower()

        # A. Direct Video File
        if is_direct_video_file_url(url_cand):
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_DIRECT_STREAM,
                normalized_url=url_cand,
                confidence_score=100
            )

        # B. Direct High-Speed Cloud Storage CDN / Worker
        if is_direct_cdn(netloc) or "workers.dev" in netloc:
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_DIRECT_STREAM,
                normalized_url=url_cand,
                confidence_score=95
            )

        # C. Movie Portal (VegaMovies, OlaMovies, KatmovieHD, CineFreak, HDHub4u)
        if is_known_movie_network(netloc):
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_MOVIE_PORTAL,
                normalized_url=url_cand,
                target_site=extract_root_domain(netloc),
                confidence_score=95
            )

        # D. Video Embed Host (StreamWish, FileLions, DoodStream, FileMoon)
        if is_video_embed_host(netloc):
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_VIDEO_HOST,
                normalized_url=url_cand,
                confidence_score=95
            )

        # E. Shortener / Ad-Gate / Container (OUO, GPLinks, FastForward 400+, Filecrypt, Droplink, etc.)
        from ..universal_bypasser.classifier import URLClassifier
        from ..universal_bypasser.adgates.fastforward_rules import FastForwardRules
        from ..universal_bypasser.models import GateType

        if is_known_shortener(netloc) or FastForwardRules.match(url_cand):
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_SHORTENER,
                normalized_url=url_cand,
                confidence_score=98,
            )

        gate_type, _ = URLClassifier.classify(url_cand)
        if gate_type in (GateType.AD_GATE, GateType.CONTAINER, GateType.CLOUD_GATE):
            return ClassifiedExecutionPlan(
                raw_input=text,
                intent=InputIntent.URL_SHORTENER,
                normalized_url=url_cand,
                confidence_score=98,
            )

        # F. Other generic website URL
        return ClassifiedExecutionPlan(
            raw_input=text,
            intent=InputIntent.URL_GENERIC_WEB,
            normalized_url=url_cand,
            confidence_score=85
        )

    # 3. Check for AI Copilot / Conversational Assistant Intent
    text_lower = text.lower()
    ai_triggers = [
        "what can you do", "what can this ai do", "what can i do",
        "how do i", "how to", "what features", "what options", "who are you",
        "ai help", "help me", "explain ripper", "what is ripper",
    ]
    if any(k in text_lower for k in ai_triggers) or (
        text_lower in ("help", "commands", "options", "features", "ai", "copilot")
    ):
        ai_copilot_resp = None
        try:
            from ..ai_engine import answer_user_query
            ai_copilot_resp = answer_user_query(text)
        except Exception:
            pass

        return ClassifiedExecutionPlan(
            raw_input=text,
            intent=InputIntent.AI_ASSISTANT,
            confidence_score=99,
            ai_plan=ai_copilot_resp,
        )

    # 4. Natural Language Search Intent (Movie or TV Series)
    query_specs = parse_query_intent(text)
    intent = InputIntent.SEARCH_TV_SERIES if query_specs.is_tv_series else InputIntent.SEARCH_MOVIE

    ai_plan_obj = None
    try:
        from ..ai_engine import parse_query_ai
        ai_plan_obj = parse_query_ai(text)
    except Exception:
        pass

    return ClassifiedExecutionPlan(
        raw_input=text,
        intent=intent,
        query_specs=query_specs,
        confidence_score=90,
        ai_plan=ai_plan_obj,
    )
