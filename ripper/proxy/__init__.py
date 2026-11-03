"""
Ripper Local Streaming Reverse Proxy Package.
Enables header spoofing, HTTP 206 Range requests, and HLS prefetching for PotPlayer/VLC.
"""
from .range_handler import parse_range_header, format_content_range
from .token_keeper import GLOBAL_TOKEN_KEEPER
from .buffer import GLOBAL_STREAM_BUFFER
from .png_stripper import strip_fake_png_header, is_fake_png_stream

def __getattr__(name: str):
    if name in ("LOCAL_PROXY_PORT", "ensure_proxy_running", "get_proxied_stream_url", "get_web_player_url"):
        from .. import proxy_engine
        return getattr(proxy_engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "LOCAL_PROXY_PORT",
    "ensure_proxy_running",
    "get_proxied_stream_url",
    "get_web_player_url",
    "parse_range_header",
    "format_content_range",
    "GLOBAL_TOKEN_KEEPER",
    "GLOBAL_STREAM_BUFFER",
    "strip_fake_png_header",
    "is_fake_png_stream",
]