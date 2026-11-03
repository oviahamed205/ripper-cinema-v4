"""
Modular Deep Portal Resolvers Registry.
Provides dedicated, isolated resolvers for VegaMovies, HDHub4u, OlaMovies,
KatmovieHD, CineFreak, PixelDrain, and BollyFlix with zero cross-file dependencies.
"""

from typing import List, Optional
import httpx

from .base import BasePortalResolver, PortalStreamResult, safe_get
from .hdhub4u import HDHub4uPortal, decrypt_hdhub4u_gadgetsweb_token
from .vegamovies import VegaMoviesPortal
from .olamovies import OlaMoviesPortal
from .katmoviehd import KatmovieHDPortal, CineFreakPortal, PixelDrainPortal
from .bollyflix import BollyFlixPortal
from .moviebox import MovieBoxPortal
from .fourkhdhub import FourKHdHubPortal

ALL_PORTAL_RESOLVERS: List[BasePortalResolver] = [
    HDHub4uPortal(),
    VegaMoviesPortal(),
    OlaMoviesPortal(),
    KatmovieHDPortal(),
    CineFreakPortal(),
    PixelDrainPortal(),
    BollyFlixPortal(),
    MovieBoxPortal(),
    FourKHdHubPortal(),
]


async def resolve_portal_url(client: httpx.AsyncClient, url: str) -> List[PortalStreamResult]:
    """Finds the matching portal and extracts all direct stream results."""
    for portal in ALL_PORTAL_RESOLVERS:
        if portal.can_handle(url):
            res = await portal.resolve(client, url)
            if res:
                return res
    return []


__all__ = [
    "BasePortalResolver",
    "PortalStreamResult",
    "safe_get",
    "HDHub4uPortal",
    "VegaMoviesPortal",
    "OlaMoviesPortal",
    "KatmovieHDPortal",
    "CineFreakPortal",
    "PixelDrainPortal",
    "BollyFlixPortal",
    "MovieBoxPortal",
    "FourKHdHubPortal",
    "ALL_PORTAL_RESOLVERS",
    "resolve_portal_url",
    "decrypt_hdhub4u_gadgetsweb_token",
]