"""
ripper.universal_engine
~~~~~~~~~~~~~~~~~~~~~~~

Autonomous, zero-maintenance multi-tier media extraction and streaming engine:
- Tier 1: Semantic Heuristic DOM Extractor (Ultra-fast, zero-browser)
- Tier 2: Headless Dynamic Engine & Real-Time Stream Sniffer (Playwright + CDP)
- Tier 3: Cloud JS Scraper Bridge (Firecrawl API)
- Tier 4: LLM Structural DOM Parser (OpenAI JSON Structured Fallback)
"""

from .pipeline import UniversalPipeline, universal_extract_media
from .heuristics import SemanticHeuristicExtractor
from .sniffer import HeadlessStreamSniffer
from .firecrawl_bridge import FirecrawlCloudBridge
from .llm_extractor import LLMStructuralExtractor

__all__ = [
    "UniversalPipeline",
    "universal_extract_media",
    "SemanticHeuristicExtractor",
    "HeadlessStreamSniffer",
    "FirecrawlCloudBridge",
    "LLMStructuralExtractor",
]
