"""Explicit resolver boundary: basic public-link traversal or existing Ripper."""
from __future__ import annotations
from typing import Protocol
from urllib.parse import urljoin,urlsplit
from bs4 import BeautifulSoup
from .discovery import MEDIA_EXTENSIONS,harvest_candidates
from .transport import Transport,ResolverClient
from .verification import signature


class Resolver(Protocol):
    async def resolve(self,url: str) -> str: ...


class ResolveError(Exception): pass


class BasicResolver:
    """Normal HTTP redirects, media elements and visible links only.

    Not a replacement for domain-specific Ripper handlers; no browser/WAF bypass.
    """
    def __init__(self,http: Transport):self.http=http

    async def resolve(self,url):
        seen=set()
        for _ in range(self.http.config.resolve_hops):
            if url in seen:raise ResolveError("resolution_loop")
            seen.add(url)
            if urlsplit(url).path.lower().endswith(MEDIA_EXTENSIONS):return url
            r=await self.http.fetch(url,max_bytes=self.http.config.max_html_bytes)
            if r.status not in {200,206}:raise ResolveError(f"resolver_http_{r.status}")
            if signature(r.body) or r.body.lstrip().startswith(b"#EXTM3U"):return r.url
            candidates=harvest_candidates(r.text,r.url,limit=1)
            if candidates:
                url=candidates[0];continue
            soup=BeautifulSoup(r.text,"html.parser")
            meta=soup.find("meta",attrs={"http-equiv":lambda x:x and x.lower()=="refresh"})
            if meta:
                content=meta.get("content","")
                import re
                found=re.search(r"url\s*=\s*(.+)",content,re.I)
                if found:
                    url=urljoin(r.url,found[1].strip().strip("\"'"));continue
            raise ResolveError("no_supported_media_link")
        raise ResolveError("resolver_hop_limit")


class RipperResolver:
    """Adapter to the user's existing Ripper installation, never a second copy.

    Legacy handlers must honor the supplied async client. Handlers that open their
    own clients are outside our transport counters/limits; see docs/INTEGRATION.md.
    """
    def __init__(self,http: Transport):
        try:
            from ripper.resolver.engine import ResolverEngine
        except Exception:
            raise RuntimeError("Ripper adapter unavailable. Install the original Ripper project and its dependencies; use --resolver basic only for ordinary media links.") from None
        self.engine=ResolverEngine(max_depth=http.config.resolve_hops,timeout=http.config.request_timeout)
        self.client=ResolverClient(http)

    async def resolve(self,url):
        result=await self.engine.resolve(url,client=self.client,use_cache=False)
        if result and result.is_success and result.final_url:
            # If resolution stopped at an intermediate generator portal (e.g. links.hdmovieshub, links.kmhd),
            # execute a 2nd hop to extract the inner Cloudflare R2 / V-Cloud / PixelDrain stream
            final_low = result.final_url.lower()
            # If resolution stopped at an intermediate generator portal (e.g. links.hdmovieshub, links.kmhd, linkos, gdflix)
            if any(portal in final_low for portal in ("links.hdmovieshub", "links.kmhd", "hubcloud.foo", "hubcloud.club", "katmoviehd", "linkos.club", "gdflix", "magiclinks")):
                try:
                    r2 = await self.client.get(result.final_url)
                    if r2.status_code == 200 and r2.text:
                        from ripper.resolver.handlers.article_crawler import extract_cloud_urls_from_html, extract_server_options_from_html
                        cloud_cands = extract_cloud_urls_from_html(r2.text)
                        # Check direct Cloudflare R2 mirrors first for highest speed
                        for cu in cloud_cands:
                            if "r2.dev" in cu.lower():
                                return cu
                        for lbl, opt in extract_server_options_from_html(r2.text, result.final_url):
                            if "r2.dev" in opt.lower():
                                return opt
                        # If no direct R2, unpack nested gateways (e.g. linkos -> gdflix -> r2)
                        for lbl, opt in extract_server_options_from_html(r2.text, result.final_url):
                            if any(k in opt.lower() for k in ("gdflix", "r2.dev", "pixeldrain")):
                                r3 = await self.client.get(opt)
                                if r3.status_code == 200 and r3.text:
                                    for sub_lbl, sub_opt in extract_server_options_from_html(r3.text, opt):
                                        if "r2.dev" in sub_opt.lower():
                                            return sub_opt
                                    for sub_c in extract_cloud_urls_from_html(r3.text):
                                        if "r2.dev" in sub_c.lower():
                                            return sub_c
                        # Normal fallback
                        for cu in cloud_cands:
                            sub_res = await self.engine.resolve(cu, client=self.client, use_cache=False)
                            if sub_res and sub_res.is_success and sub_res.final_url:
                                return sub_res.final_url
                        for lbl, opt in extract_server_options_from_html(r2.text, result.final_url):
                            if opt != result.final_url:
                                sub_res = await self.engine.resolve(opt, client=self.client, use_cache=False)
                                if sub_res and sub_res.is_success and sub_res.final_url:
                                    return sub_res.final_url
                except Exception:
                    pass
            return result.final_url
        raise ResolveError("ripper_resolution_failed")
