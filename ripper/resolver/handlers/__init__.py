"""
Automatically registers all site-specific resolver plugins into GLOBAL_REGISTRY.
"""
from ..registry import GLOBAL_REGISTRY
from .cloud_storage import CloudStorageHandler
from .file_lockers import FileLockersHandler
from .hubcloud import HubCloudHandler
from .kmhd import KMHDHandler, resolve_kmhd_page
from .vcloud import VCloudHandler, resolve_vcloud_page
from .vegamovies_vcloud import VegaMoviesVCloudHandler
from .hdhub4u_hubcloud import HDHub4uHandler
from .magiclinks import MagicLinksHandler, resolve_magiclinks_page
from .nexdrive import NexDriveHandler, resolve_nexdrive_page
from .olamovies import OlaMoviesHandler, resolve_olamovies_page
from .gdtot import GDToTHandler
from .appdrive import AppDriveHandler
from .ad_shorteners import AdShortenersHandler
from .filecrypt import FileCryptHandler
from .video_hosts import VideoHostsHandler
from .universal_heuristics import UniversalHeuristicsHandler
from .article_crawler import (
    crawl_intermediate_server_page,
    resolve_to_direct_stream_url,
    extract_server_options_from_html,
    extract_cloud_urls_from_html,
)


def register_all_handlers() -> None:
    """Register all built-in site handlers in priority order."""
    handlers = [
        CloudStorageHandler(),
        VideoHostsHandler(),
        FileLockersHandler(),
        HubCloudHandler(),
        KMHDHandler(),
        VCloudHandler(),
        VegaMoviesVCloudHandler(),
        HDHub4uHandler(),
        MagicLinksHandler(),
        NexDriveHandler(),
        OlaMoviesHandler(),
        GDToTHandler(),
        AppDriveHandler(),
        AdShortenersHandler(),
        FileCryptHandler(),
        UniversalHeuristicsHandler(),
    ]


    for h in handlers:
        GLOBAL_REGISTRY.register(h)


register_all_handlers()

__all__ = [
    "CloudStorageHandler",
    "FileLockersHandler",
    "HubCloudHandler",
    "KMHDHandler",
    "VCloudHandler",
    "VegaMoviesVCloudHandler",
    "HDHub4uHandler",
    "MagicLinksHandler",
    "NexDriveHandler",
    "OlaMoviesHandler",
    "GDToTHandler",
    "AppDriveHandler",
    "AdShortenersHandler",
    "FileCryptHandler",
    "UniversalHeuristicsHandler",

    "crawl_intermediate_server_page",
    "resolve_to_direct_stream_url",
    "extract_server_options_from_html",
    "extract_cloud_urls_from_html",
    "resolve_kmhd_page",
    "resolve_vcloud_page",
    "resolve_magiclinks_page",
    "resolve_nexdrive_page",
    "resolve_olamovies_page",
    "register_all_handlers",
]