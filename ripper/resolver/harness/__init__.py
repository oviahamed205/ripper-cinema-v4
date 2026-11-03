"""
Adversarial Live Stream Test Harness for Ripper Resolver.
Executes live acquisition, anti-bot evasion, and binary stream verification via ffprobe.
"""
from .runner import (
    OmegaHarness,
    StealthSession,
    verify_binary_stream,
    harvest_post_download_candidates,
    TARGET_SITES,
)

__all__ = [
    "OmegaHarness",
    "StealthSession",
    "verify_binary_stream",
    "harvest_post_download_candidates",
    "TARGET_SITES",
]
