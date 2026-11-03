"""
AnyStream Engine: Universal Video Stream Extractor.
Coordinates decoders, URL sanitization, and direct stream extraction.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .base_decoder import StreamInfo
from .decoders import ANYSTREAM_REGISTRY


class AnyStreamEngine:
    """Extracts direct streamable video URLs from any host or page."""

    async def extract_stream(self, url: str, html: Optional[str] = None) -> Optional[StreamInfo]:
        """Extract best direct stream from URL."""
        decoder = ANYSTREAM_REGISTRY.get_decoder(url, html or "")
        return await decoder.decode(url, html)


GLOBAL_ANYSTREAM = AnyStreamEngine()