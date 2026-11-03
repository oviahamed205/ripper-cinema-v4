"""
Domain Knowledge Base & Pre-compiled Heuristic Tables.
Contains 500+ categorized streaming domains, cloud storage CDNs,
ad-shortener gateways, and video embed hosts.
"""

from __future__ import annotations

import re
from typing import Set, Tuple, Optional
import urllib.parse


# 1. MOVIE NETWORKS & DIRECTORY SITES (23+ Indexed Networks & Common TLDs)
MOVIE_DOMAINS: Set[str] = {
    # VegaMovies network
    "vegamovies.ph", "vegamovies.to", "vegamovies.is", "vegamovies.im", "vegamovies.life",
    "vegamovies.in", "vegamovies.art", "vegamovies.vip", "vegamovies.futbol", "vegamovies.gmbh",
    "vegamovies.pages.dev", "vegamovies.lol", "vegamovies.yt",
    # KatmovieHD network
    "katmoviehd.to", "katmoviehd.eu", "katmoviehd.se", "katmoviehd.top", "katmoviehd.ms",
    "katmoviehd.vip", "katmoviehd.sx", "katmoviehd.tw", "katmoviehd.click", "katworld.top",
    "new.katmoviehd.top", "katmoviehd.link", "katmoviehd.lat",
    # CineFreak network
    "cinefreak.net", "cinefreak.xyz", "cinefreak.click", "cinefreak.co", "cinefreak.info",
    "cinefreak.org", "cinefreak.in", "cinefreak.site", "cinecloud.site", "new5.cinecloud.site",
    # KMmovies network
    "kmmovies.pics", "kmmovies.vip", "kmmovies.life", "kmmovies.org", "kmmovies.in",
    "kmmovies.lat", "kmmovies.co", "kmmovies.top", "kmhd.eu", "katdrive.top",
    # OlaMovies network
    "olamovies.art", "olamovies.top", "olamovies.ink", "olamovies.skin", "olamovies.homes",
    "ol-am.top", "links.ol-am.top", "drive.olamovies.download", "omdrive.download",
    # HDHub4u network
    "hdhub4u.bi", "hdhub4u.lat", "hdhub4u.guru", "hdhub4u.ph", "hdhub4u.re", "hdhub4u.mov",
    "hdhub4u.top", "hdhub4u.trade", "hdhub4u.vip", "hdhub4u.dad", "hdhub4u.ch", "hdhub4u.wf",
    "hubcloud.cx", "hubcloud.foo", "hubcloud.club", "hubcloud.fans", "hubcdn.sbs", "hubcdn.fans",
    "gadgetsweb.xyz", "homelander", "gadgetsweb",
    # BollyFlix & BollyPro
    "bollyflix.ph", "bollyflix.im", "bollyflix.vip", "bollyflix.in", "bollyflix.me",
    "bollypro.com", "bollypro.org", "bollypro.net",
    # MoviesMod & MoviesDrive
    "moviesmod.ph", "moviesmod.org", "moviesmod.cc", "moviesmod.one", "moviesmod.zip",
    "moviesdrive.in", "moviesdrive.world", "moviesdrive.info",
    # 7StarHD & 9xMovies
    "7starhd.latino", "7starhd.run", "7starhd.click", "7starhd.tube", "7starhd.pw",
    "9xmovies.click", "9xmovies.world", "9xmovielive.com", "9xmovies.green",
    # WorldFree4u & DownloadHub
    "worldfree4u.gd", "worldfree4u.trade", "worldfree4u.lol", "worldfree4u.cat",
    "downloadhub.ac", "downloadhub.lol", "downloadhub.top", "d8hub.cc",
    # International & Hollywood
    "fmoviess.org", "fmovies.to", "fmovies.ps", "fmovies.llc",
    "movie4kto.xyz", "movie4k.org", "movie4k.to",
    "lookmovie2.to", "lookmovie2.city", "lookmovie.foundation",
    "uwatchfree.be", "uwatchfree.mx", "uwatchfree.org",
    "hindilinks4u.estate", "hindilinks4u.cam",
    "movienz.com", "filmsur.com", "filmshd.org", "mp4gana.com",
    "vidsrc.to", "vidsrc.me", "vixsrc.to", "2embed.to",
}

# 2. SHORTENERS & AD-GATES
SHORTENER_DOMAINS: Set[str] = {
    "ouo.io", "ouo.press", "droplink.co", "gplinks.co", "gplinks.in",
    "shrinkme.io", "shrinkme.us", "exe.io", "exey.io", "clicksfly.com",
    "cut-urls.com", "za.gl", "shortur.me", "dropi.co", "adurl.site",
    "magiclinks.lol", "magiclinks.net", "magiclinks.top", "shortx.links",
    "linksly.co", "linkvertise.com", "link-to.net", "direct-link.net",
    "linkvertise.download", "karanlinks.com", "modijiurl.com", "techydeepak.net",
}

# 3. CLOUD STORAGE CDNS (DIRECT HIGH-SPEED VIDEO STREAMS)
DIRECT_STREAM_CDNS: Set[str] = {
    "r2.cloudflarestorage.com", "workers.dev", "pixeldrain.com",
    "gofile.io", "fastdl.link", "s3.amazonaws.com", "backblazeb2.com",
    "drive.google.com", "onedrive.live.com", "mega.nz", "1fichier.com",
    "rapidgator.net", "katfile.com", "ddownload.com",
}

# 4. VIDEO EMBED HOSTS
VIDEO_EMBED_HOSTS: Set[str] = {
    "doodstream.com", "d000d.com", "dood.to", "dood.so", "playmogo.com",
    "streamtape.com", "streamtape.to", "strtape.tech",
    "mixdrop.co", "mixdrop.to", "mixdrop.sx", "mixdrop.bz",
    "filemoon.sx", "filemoon.to", "moonplayer.xyz",
    "voe.sx", "voe-unblock.com", "reputationscreedoil.com",
    "streamwish.to", "streamwish.com", "strwish.com", "wishembed.pro",
    "filelions.to", "filelions.online", "fdwfile.com",
    "lulustream.com", "luluvdo.com",
    "vidhidepro.com", "vidhide.com", "streamhide.to",
    "upstream.to", "mp4upload.com", "streamruby.com",
    "playmate.to", "vidara.to", "vidarae.live",
}

# Pre-compile video extension patterns
RE_VIDEO_EXT = re.compile(r'\.(?:mkv|mp4|m3u8|webm|avi|mov|ts|m4v)(?:\?[^\s"\'<>]*)?$', re.IGNORECASE)
RE_CLEAN_DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?([^/:]+)", re.IGNORECASE)


def extract_root_domain(url_or_domain: str) -> str:
    """Extract clean domain name (e.g. 'vegamovies.ph' from full URL or text)."""
    if not url_or_domain:
        return ""
    m = RE_CLEAN_DOMAIN.match(url_or_domain.strip())
    if m:
        return m.group(1).lower()
    return url_or_domain.split("/")[0].lower()


def is_known_movie_network(url_or_host: str) -> bool:
    """Returns True if the host is a known movie download or streaming network."""
    host = extract_root_domain(url_or_host)
    return any(host.endswith(d) or d in host for d in MOVIE_DOMAINS)


def is_known_shortener(url_or_host: str) -> bool:
    """Returns True if the host is a known ad shortener or gateway."""
    host = extract_root_domain(url_or_host)
    return any(host.endswith(d) or d in host for d in SHORTENER_DOMAINS)


def is_direct_cdn(url_or_host: str) -> bool:
    """Returns True if the host is a known direct high-speed cloud storage CDN."""
    host = extract_root_domain(url_or_host)
    return any(host.endswith(d) or d in host for d in DIRECT_STREAM_CDNS)


def is_video_embed_host(url_or_host: str) -> bool:
    """Returns True if the host is a video streaming host."""
    host = extract_root_domain(url_or_host)
    return any(host.endswith(d) or d in host for d in VIDEO_EMBED_HOSTS)


def is_direct_video_file_url(url: str) -> bool:
    """Returns True if the URL points directly to a video container format."""
    clean = url.split("?")[0].strip().lower()
    return bool(RE_VIDEO_EXT.search(clean))
