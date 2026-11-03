"""
SITE DATABASE: Persistent storage wrapper for all discovered movie sites.
"""
from .site_hunter import SiteHunter, DiscoveredSite

__all__ = ["SiteHunter", "DiscoveredSite"]
