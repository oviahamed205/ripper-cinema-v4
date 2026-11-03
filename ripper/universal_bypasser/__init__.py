"""
Universal Shortlink Bypasser, Ad-Gate Solver & Encrypted Container Engine.
"""

from ripper.universal_bypasser.classifier import URLClassifier
from ripper.universal_bypasser.cnl import CNL2Crypto, CNL2Listener
from ripper.universal_bypasser.engine import UniversalBypasserEngine
from ripper.universal_bypasser.models import (
    BypassContext,
    CNLPayload,
    ContainerResult,
    GateType,
    ShortlinkResult,
)

__all__ = [
    "UniversalBypasserEngine",
    "URLClassifier",
    "GateType",
    "ShortlinkResult",
    "ContainerResult",
    "BypassContext",
    "CNLPayload",
    "CNL2Crypto",
    "CNL2Listener",
    "bypass_url",
    "unroll_folder",
]


async def bypass_url(url: str, context: BypassContext | None = None) -> ShortlinkResult:
    """Convenience helper to bypass a single shortlink or ad-gate URL."""
    engine = UniversalBypasserEngine(context)
    return await engine.bypass_shortlink(url)


async def unroll_folder(url: str, context: BypassContext | None = None) -> ContainerResult:
    """Convenience helper to unroll a container, locker, or folder URL."""
    engine = UniversalBypasserEngine(context)
    return await engine.unroll_container(url)
