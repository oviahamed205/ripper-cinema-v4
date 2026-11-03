"""
Universal URL Classifier & Gate Detection Engine.
Inspects domains, URI paths, and query parameters to determine the appropriate
handling pipeline (FastForward redirect, AdGate solver, Container unroller, or CloudGate).
"""

from __future__ import annotations

import base64
import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from ripper.universal_bypasser.models import GateType


class URLClassifier:
    """Classifies target URLs and routes them to specialized bypass handlers."""

    # Simple redirect query parameters frequently used in wrapper links
    REDIRECT_PARAM_NAMES = {
        "url", "link", "target", "dest", "destination", "redirect", "r",
        "to", "out", "go", "u", "uri", "q", "href", "forward"
    }

    # Domains known for direct simple redirects
    SIMPLE_REDIRECT_DOMAINS = {
        "bit.ly", "tinyurl.com", "t.co", "is.gd", "buff.ly", "ow.ly",
        "cutt.ly", "rb.gy", "rebrand.ly", "shorturl.at", "bl.ink",
        "t.ly", "v.gd", "git.io", "aka.ms", "goo.gl"
    }

    # AdGate domains
    ADGATE_PATTERNS = {
        "gplinks": [r"gplinks\.(?:co|com|in)"],
        "droplink": [r"droplink\.(?:co|io)", r"dropeps\.(?:com|co)", r"dropgalaxy\.(?:com|in)"],
        "rocklinks": [r"rocklinks\.(?:net|in|top|fun|io)"],
        "ouo": [r"ouo\.(?:io|press)"],
        "sub2unlock": [
            r"sub2unlock\.(?:com|net)",
            r"sub4unlock\.(?:com|net)",
            r"social-unlock\.(?:com|net)",
            r"rekonise\.com",
            r"boost\.ink",
            r"mboost\.me",
        ],
        "shareus": [
            r"shareus\.io",
            r"shrs\.link",
            r"mdiskshortner\.(?:link|com)",
        ],
        "shrinkearn": [
            r"shrinkearn\.com",
            r"shrinkforearn\.(?:in|net)",
            r"earn4link\.com",
        ],
        "cloud_drive_gate": [
            r"katdrive\.net",
            r"gadrive\.com",
            r"sharer\.pw",
            r"drivehub\.me",
            r"kolop\.net",
            r"gdtot\.(?:pro|top)",
        ],
        "adfly": [
            r"adf\.ly",
            r"j\.gs",
            r"q\.gs",
            r"ay\.gy",
            r"tinyium\.com",
            r"microify\.com",
            r"kudoflow\.com",
            r"streamvoyage\.com",
        ],
        "psa_wf": [
            r"psa\.wf",
            r"go2\.pics",
            r"cashgrowth\.online",
            r"ravellawfirm\.com",
            r"themezon\.net",
            r"fc\.lc",
            r"tpi\.li",
            r"oii\.la",
        ],
        "try2link": [
            r"try2link\.(?:com|net|org|link)",
        ],
        "bstlar": [
            r"bstlar\.(?:com|io)",
            r"bst\.gg",
        ],
        "generic_fly": [
            r"shrinkme\.(?:io|org|us)",
            r"adlinkfly\.(?:com|in)",
            r"exe\.(?:io|app)",
            r"shorte\.(?:st|pe)",
            r"vurl\.(?:com|co)",
            r"clk\.(?:sh|ink)",
            r"linkrex\.(?:net|co)",
            r"za\.gl",
            r"cut-urls\.(?:com)",
            r"shortzones\.(?:com)",
        ]
    }

    # Container and folder lockers
    CONTAINER_PATTERNS = {
        "filecrypt": [r"filecrypt\.(?:cc|co|to|net)"],
        "keeplinks": [r"keeplinks\.(?:org|co|com)"],
        "pastebin": [r"pastebin\.com", r"rentry\.(?:co|org)", r"justpaste\.(?:it|me)", r"controlc\.com"],
        "paster_so": [r"paster\.(?:so|gg)", r"pasteshr\.com"],
        "linkbox": [r"linkbox\.to", r"telebox\.(?:fun|me)"],
    }

    # Cloud Turnstile / Interstitial gates
    CLOUDGATE_PATTERNS = {
        "linkvertise": [
            r"linkvertise\.(?:com|net)",
            r"link-to\.net",
            r"up-to-down\.net",
            r"direct-link\.net",
            r"file-link\.net",
            r"linkvertise\.download",
        ],
        "lootlabs": [
            r"loot-link\.com",
            r"loot-links\.com",
            r"lootlinks\.co",
            r"lootlabs\.gg",
            r"lootdest\.com",
        ],
        "workink": [
            r"work\.ink",
            r"workink\.(?:net|org)",
        ]
    }

    # Known direct streaming / hoster domains
    DIRECT_HOSTER_DOMAINS = {
        "drive.google.com", "mega.nz", "pixeldrain.com", "1fichier.com",
        "mediafire.com", "gofile.io", "krakenfiles.com", "dropbox.com",
        "streamtape.com", "streamtape.net", "streamtape.to", "streamta.pe",
        "doodstream.com", "dood.so", "dood.to", "dood.wf", "dood.cx",
        "mixdrop.co", "mixdrop.to", "mixdrop.sx", "mixdrop.bz",
        "vidguard.to", "vgfplay.com", "vembed.net",
        "filemoon.sx", "filemoon.to",
        "mp4upload.com", "streamwish.to", "streamwish.com",
        "voe.sx", "supervideo.tv", "upstream.to", "vidsrc.me", "vidsrc.to"
    }

    @classmethod
    def extract_embedded_redirect(cls, url: str) -> Optional[str]:
        """
        Detects if the URL embeds the target destination inside a query parameter,
        e.g., https://wrapper.com/out?url=https://streamtape.com/v/123
        or base64 encoded destination.
        """
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            for param_name in cls.REDIRECT_PARAM_NAMES:
                if param_name in query_params and query_params[param_name]:
                    candidate = query_params[param_name][0]
                    # Check plain URL
                    if candidate.startswith(("http://", "https://")):
                        return candidate
                    # Check url-encoded URL
                    decoded = unquote(candidate)
                    if decoded.startswith(("http://", "https://")):
                        return decoded
                    # Check base64 encoded URL
                    try:
                        b64_decoded = base64.b64decode(candidate.encode()).decode("utf-8", errors="ignore")
                        if b64_decoded.startswith(("http://", "https://")):
                            return b64_decoded
                    except Exception:
                        pass

            # Check path segments for base64 encoded target URLs
            path_parts = [p for p in parsed.path.strip("/").split("/") if len(p) >= 12]
            for seg in path_parts:
                try:
                    pad = (4 - len(seg) % 4) % 4
                    b64_candidate = seg + "=" * pad
                    b64_decoded = base64.b64decode(b64_candidate.encode()).decode("utf-8", errors="ignore")
                    if b64_decoded.startswith(("http://", "https://")):
                        return b64_decoded
                except Exception:
                    pass
        except Exception:
            pass
        return None

    @classmethod
    def classify(cls, url: str) -> Tuple[GateType, str]:
        """
        Analyzes a URL and returns a tuple of (GateType, specific_handler_key).
        Example: (GateType.AD_GATE, "gplinks") or (GateType.CONTAINER, "filecrypt")
        """
        if not url:
            return GateType.UNKNOWN, "none"

        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        # Strip port or www.
        domain = re.sub(r"^www\.", "", netloc.split(":")[0])

        # 1. Embedded query redirect check
        embedded = cls.extract_embedded_redirect(url)
        if embedded:
            return GateType.SIMPLE_REDIRECT, "embedded_param"

        # 1b. FastForward Declarative Ruleset (400+ domains instant check)
        from ripper.universal_bypasser.adgates.fastforward_rules import FastForwardRules
        if FastForwardRules.match(url):
            return GateType.SIMPLE_REDIRECT, "fastforward_rules"

        # 2. Simple redirect domains
        if domain in cls.SIMPLE_REDIRECT_DOMAINS:
            return GateType.SIMPLE_REDIRECT, "shortener_domain"

        # 3. Direct hoster check
        if domain in cls.DIRECT_HOSTER_DOMAINS or any(dh in domain for dh in cls.DIRECT_HOSTER_DOMAINS):
            return GateType.DIRECT_HOSTER, "direct_hoster"

        # 4. Containers / Link lockers
        for key, patterns in cls.CONTAINER_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, domain) or re.search(pat, url):
                    return GateType.CONTAINER, key

        # 5. Ad-Gate multi-step countdowns
        for key, patterns in cls.ADGATE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, domain) or re.search(pat, url):
                    return GateType.AD_GATE, key

        # 6. Cloud Turnstile / Interstitial gates
        for key, patterns in cls.CLOUDGATE_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, domain) or re.search(pat, url):
                    return GateType.CLOUD_GATE, key

        return GateType.UNKNOWN, "generic"
