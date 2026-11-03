"""
Ripper AnyStream Universal Video Extraction Package.
Exposes modular decoders and full backwards-compatible entrypoints.
"""
from __future__ import annotations

from .base_decoder import StreamInfo, BaseHostDecoder
from .engine import AnyStreamEngine, GLOBAL_ANYSTREAM
from .decoders import ANYSTREAM_REGISTRY

# Backwards-compatible imports from legacy
from .legacy import (
    handle_anystream_cli,
    extract_any_streams,
    sanitize_user_url,
    is_valid_video_stream,
    DOOD_HOSTS,
    DEFAULT_HEADERS,
)

__all__ = [
    "StreamInfo",
    "BaseHostDecoder",
    "AnyStreamEngine",
    "GLOBAL_ANYSTREAM",
    "ANYSTREAM_REGISTRY",
    "handle_anystream_cli",
    "extract_any_streams",
    "sanitize_user_url",
    "is_valid_video_stream",
    "DOOD_HOSTS",
    "DEFAULT_HEADERS",
]