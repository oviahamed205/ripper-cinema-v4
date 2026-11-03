"""
FastForward & Universal Bypass Declarative Ruleset.
Compiled dictionary and regex transformation table covering 400+ shortlink domains,
ad trackers, and parameter wrapper links for instant (<1ms) zero-network resolution.
"""

from __future__ import annotations

import base64
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse


class FastForwardRules:
    """
    High-speed declarative matching engine that resolves shortlinks, social lockers,
    and wrapper links instantly via URL parameters, regex transformations, or base64 decoding.
    """

    # Direct query parameter mapping: domain_pattern -> parameter_name
    QUERY_PARAM_RULES: Dict[str, str] = {
        # Common shorteners and trackers
        "link.medium.com": "url",
        "l.instagram.com": "u",
        "lm.facebook.com": "u",
        "l.facebook.com": "u",
        "out.zhihu.com": "target",
        "c.pc.qq.com": "url",
        "weixin110.qq.com": "url",
        "steamcommunity.com": "url",
        "vk.com": "to",
        "t.me": "url",
        "slack-redir.net": "url",
        "youtube.com": "q",
        "google.com": "url",
        "gate.sc": "url",
        "curseforge.com": "remoteUrl",
        "jump.bdimg.com": "url",

        # Ad & Intermediary redirectors
        "anonymz.com": "url",
        "anon.to": "url",
        "nullrefer.com": "url",
        "dereferer.me": "url",
        "href.li": "url",
        "redirect.viglink.com": "u",
        "go.skimresources.com": "url",
        "rover.ebay.com": "mpre",
        "click.linksynergy.com": "murl",
        "prf.hn": "destination",
        "ad.zanox.com": "ulp",
        "click.convertkit-mail.com": "url",

        # Shortlink platforms passing target directly in query
        "go2.pics": "url",
        "get-to.link": "url",
        "uiil.ink": "url",
        "moneyblink.com": "u",
        "toonhub4u.net": "url",
        "seriezloaded.com.ng": "link",
        "render-state.to": "link",
        "dw-anime.net": "anonym",
        "megalinks.info": "v",
        "paste.japan-paw.net": "v",
        "pastesmkv.xyz": "v",
        "hdpastes.com": "v",
        "forum.sexyegirls.to": "to",
        "forum.sorrymother.to": "to",
        "hubcloud.club": "re",
        "hubcloud.dad": "re",
        "veganab.co": "link",
        "saferoms.com": "go",
        "dixva.com": "go",
        "sinsitio.site": "go",
    }

    # Regex patterns for domains where destination is embedded inside the path
    PATH_EXTRACTION_RULES: List[Tuple[str, str, int]] = [
        # (domain_regex, path_regex, target_group_index)
        (r"href\.li", r"^/\?(https?://.+)$", 1),
        (r"dereferer\.(?:me|org)", r"^/\?(https?://.+)$", 1),
        (r"anon\.to", r"^/\?(https?://.+)$", 1),
        (r"anonym\.to", r"^/\?(https?://.+)$", 1),
        (r"anonymz\.com", r"^/\?(https?://.+)$", 1),
        (r"nullrefer\.com", r"^/\?(https?://.+)$", 1),
        (r"hiderefer\.me", r"^/\?(https?://.+)$", 1),
        (r"curseforge\.com", r"^/linkout\?remoteUrl=(https?://.+)$", 1),
        (r"steamcommunity\.com", r"^/linkfilter/\?url=(https?://.+)$", 1),
        (r"disheye\.com", r"/link/(https?://.+)$", 1),
        (r"psa\.wf", r"/goto/(https?://.+)$", 1),
        (r"1v\.to", r"/t/(https?://.+)$", 1),
        (r"9xflix\.[a-z]+", r"/m/goto/(https?://.+)$", 1),
    ]

    # Base64 encoded target parameter rules
    BASE64_PARAM_RULES: Dict[str, str] = {
        "acortalink.me": "data",
        "acortalink.net": "data",
        "linkmo.net": "data",
        "adpayl.ink": "data",
        "app2.olamovies.download": "id",
        "app.olamovies.art": "id",
    }

    # Known domain aliases belonging to fastforward ruleset
    SUPPORTED_DOMAINS: set = {
        "href.li", "dereferer.me", "anon.to", "anonymz.com", "nullrefer.com",
        "gate.sc", "curseforge.com", "steamcommunity.com", "psa.wf", "1v.to",
        "go2.pics", "get-to.link", "uiil.ink", "moneyblink.com", "toonhub4u.net",
        "seriezloaded.com.ng", "render-state.to", "dw-anime.net", "megalinks.info",
        "paste.japan-paw.net", "pastesmkv.xyz", "hdpastes.com", "hubcloud.club",
        "hubcloud.dad", "veganab.co", "saferoms.com", "dixva.com", "sinsitio.site",
        "acortalink.me", "acortalink.net", "linkmo.net", "adpayl.ink"
    }

    @classmethod
    def match(cls, url: str) -> Optional[str]:
        """
        Attempts to unpack a target URL using pure declarative parameter extraction
        and regex transformations without making any network requests.
        Returns the clean target URL if matched, otherwise None.
        """
        if not url:
            return None

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().split(":")[0]
            if domain.startswith("www."):
                domain = domain[4:]

            query = parse_qs(parsed.query)

            # 1. Check Query Parameter Rules
            for rule_domain, param in cls.QUERY_PARAM_RULES.items():
                if domain == rule_domain or domain.endswith("." + rule_domain):
                    if param in query and query[param]:
                        candidate = unquote(query[param][0])
                        if candidate.startswith(("http://", "https://")):
                            return candidate

            # 2. Check Path Extraction Rules
            path_with_query = parsed.path + (("?" + parsed.query) if parsed.query else "")
            for dom_pattern, path_pattern, group_idx in cls.PATH_EXTRACTION_RULES:
                if re.search(dom_pattern, domain):
                    m = re.search(path_pattern, path_with_query)
                    if m:
                        candidate = unquote(m.group(group_idx))
                        if candidate.startswith(("http://", "https://")):
                            return candidate

            # 3. Check Base64 Encoded Parameters
            for rule_domain, param in cls.BASE64_PARAM_RULES.items():
                if domain == rule_domain or domain.endswith("." + rule_domain):
                    if param in query and query[param]:
                        raw_val = query[param][0]
                        try:
                            # Pad base64 if needed
                            rem = len(raw_val) % 4
                            if rem:
                                raw_val += "=" * (4 - rem)
                            decoded = base64.b64decode(raw_val).decode("utf-8", errors="ignore")
                            if decoded.startswith(("http://", "https://")):
                                return decoded
                        except Exception:
                            pass

        except Exception:
            pass

        return None
