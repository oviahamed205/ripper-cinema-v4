"""
Anti-Honeypot, CSS Trap, and Ad-Network Filter for Ripper Resolver.
Detects invisible scraper traps (display:none, opacity:0, hidden off-screen)
and discards known ad network redirects and malvertising traps.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple


AD_TRAP_DOMAINS: Set[str] = {
    "goodpics.net", "propellerads.com", "adsterra.com", "popads.net",
    "clickadu.com", "trafficjunky.com", "exoclick.com", "hilltopads.com",
    "monetag.com", "yuhuads.com", "ad-maven.com", "richads.com",
    "adcash.com", "juicyads.com", "zeroredirect.com", "adxcore.com",
    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
    "trafficstars.com", "popcash.net", "adtrue.com", "infolinks.com",
    "media.net", "adblade.com", "mgid.com", "revcontent.com",
    "outbrain.com", "taboola.com", "adsupply.com", "bidvertiser.com",
    "vglist.cv", "vglist.top", "vglist.nl", "vegamovies-apk.com", "vegamovies.click", "vegamovies.yt",
}

AD_PATH_PATTERNS = (
    re.compile(r"/(?:ads?|banner|click|pop|tracking|bannerid|affiliate|zoneid|delivery|serve-ad|promo|sponsor)/", re.I),
    re.compile(r"[?&](?:ad_id|aff_id|click_id|tracking_id|zoneid|camp_id|ref_id)=", re.I),
)

HIDDEN_CSS_PATTERNS = (
    re.compile(r"display\s*:\s*none", re.I),
    re.compile(r"visibility\s*:\s*hidden", re.I),
    re.compile(r"opacity\s*:\s*0(?:\.0+)?(?:\s*;|\s*$)", re.I),
    re.compile(r"width\s*:\s*0(?:px)?(?:\s*;|\s*$)", re.I),
    re.compile(r"height\s*:\s*0(?:px)?(?:\s*;|\s*$)", re.I),
    re.compile(r"font-size\s*:\s*0(?:px)?(?:\s*;|\s*$)", re.I),
    re.compile(r"(?:left|top|right|bottom)\s*:\s*-\d{3,}px", re.I),
)

HONEYPOT_CLASS_KEYWORDS = {
    "honeypot", "honey-pot", "trap", "bot-trap", "fake-link",
    "invisible", "hidden-link", "anti-bot", "d-none", "sr-only",
}


def host_of(url: str) -> str:
    """Return lowercase hostname of URL, or empty string."""
    if not url:
        return ""
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_ad_trap(url: str) -> bool:
    """Detect if URL points to a known ad network, tracker, sponsor, or popup trap."""
    if not url:
        return False
    try:
        host = host_of(url)
        if any(trap in host for trap in AD_TRAP_DOMAINS):
            return True
        if any(k in host for k in ["vglist", "vegamovies-apk", "apkdownload", "adsterra", "propellerads", "popcash", "popads"]):
            return True
        for pattern in AD_PATH_PATTERNS:
            if pattern.search(url):
                return True
    except Exception:
        return False
    return False


def is_hidden_element(element: Any) -> bool:
    """
    CSS-aware check for honeypots and invisible scraper traps.
    Detects inline CSS hiding, HTML hidden attributes, and trap classes.
    """
    if not element or not hasattr(element, "get"):
        return False

    try:
        if element.has_attr("hidden") or element.get("aria-hidden") == "true":
            return True

        classes = " ".join(element.get("class", [])).lower()
        if any(keyword in classes for keyword in HONEYPOT_CLASS_KEYWORDS):
            return True

        element_id = str(element.get("id", "")).lower()
        if any(keyword in element_id for keyword in HONEYPOT_CLASS_KEYWORDS):
            return True

        style = str(element.get("style", "")).lower()
        if style:
            for pattern in HIDDEN_CSS_PATTERNS:
                if pattern.search(style):
                    return True

        parent = getattr(element, "parent", None)
        if parent and hasattr(parent, "get") and parent.name != "[document]":
            parent_style = str(parent.get("style", "")).lower()
            if "display:none" in parent_style.replace(" ", ""):
                return True
            parent_classes = " ".join(parent.get("class", [])).lower()
            if any(keyword in parent_classes for keyword in HONEYPOT_CLASS_KEYWORDS):
                return True
    except Exception:
        return False

    return False