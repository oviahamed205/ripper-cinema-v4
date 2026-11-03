"""
JavaScript and Template AST Unpackers for Ripper Resolver.
Includes:
- Pure-Python Dean Edwards Packer unpacker
- SvelteKit SSR data parser (links.kmhd.eu / KatMovieHD)
- Client-side JS redirect extractors
- HTML Meta-Refresh extractors
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


from .crypto_unpacker import _clean_extracted_url, _is_followable_http_url
from .honeypot_filter import is_ad_trap


JS_REDIRECT_PATTERNS = [
    re.compile(
        r'(?:window\.)?location(?:\.href|\.replace|\.assign)?\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(r'(?:window\.)?location\.replace\(["\']([^"\']+)["\']\)', re.IGNORECASE),
    re.compile(r'(?:window\.)?location\.assign\(["\']([^"\']+)["\']\)', re.IGNORECASE),
    re.compile(r'top\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'self\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'document\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'var\s+redirect_link\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'window\.location\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'window\.open\(["\']([^"\']+)["\']', re.IGNORECASE),
]

_PACKER_PATTERN = re.compile(
    r"eval\(function\(p,a,c,k,e,[rd]\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)",
    re.DOTALL,
)


def unpack_dean_edwards_packer(packed_js: str) -> str:
    """
    Unpacks JavaScript obfuscated with Dean Edwards P.A.C.K.E.R.
    Pure-Python implementation with zero external runtime dependencies.
    """
    if not packed_js or "eval(function(p,a,c,k,e," not in packed_js:
        return packed_js

    def _base_encode(num: int, radix: int) -> str:
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if num == 0:
            return "0"
        res = []
        while num > 0:
            res.append(chars[num % radix])
            num //= radix
        return "".join(reversed(res))

    match = _PACKER_PATTERN.search(packed_js)
    if not match:
        return packed_js

    payload, radix_str, count_str, symtab_str = match.groups()
    radix = int(radix_str)
    count = int(count_str)
    symtab = symtab_str.split("|")

    words: Dict[str, str] = {}
    for i in range(count):
        key = _base_encode(i, radix)
        val = symtab[i] if i < len(symtab) and symtab[i] else key
        words[key] = val

    def _replace_word(m: re.Match) -> str:
        word = m.group(0)
        return words.get(word, word)

    unpacked = re.sub(r"\b\w+\b", _replace_word, payload)
    return unpacked.replace("\\'", "'").replace('\\"', '"')


def extract_meta_refresh_url(html_content: str, base_url: str = "") -> Optional[str]:
    """Extract destination URL from <meta http-equiv='refresh' content='X;url=...'> tag."""
    if not html_content or "refresh" not in html_content.lower():
        return None

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        meta = soup.find("meta", attrs={"http-equiv": re.compile(r"^refresh$", re.I)})
        if meta and meta.get("content"):
            content = str(meta["content"])
            match = re.search(r"url\s*=\s*['\"]?([^\s;'\"<>]+)", content, re.IGNORECASE)
            if match:
                raw_target = match.group(1).strip().strip("'\"")
                joined = urllib.parse.urljoin(base_url, raw_target) if base_url else raw_target
                cleaned = _clean_extracted_url(joined)
                if _is_followable_http_url(cleaned) and not is_ad_trap(cleaned):
                    return cleaned
    except Exception as exc:
        logger.debug("Meta refresh extraction failed: %s", exc)
        return None
    return None


def extract_js_redirect_url(html_content: str, base_url: str = "") -> Optional[str]:
    """Extract client-side JavaScript redirect URLs, checking unpacked scripts if necessary."""
    if not html_content:
        return None

    content_to_check = html_content
    if "eval(function(p,a,c,k,e," in html_content:
        content_to_check = unpack_dean_edwards_packer(html_content) + "\n" + html_content

    lowered = content_to_check.lower()
    if (
        "location" not in lowered
        and "replace" not in lowered
        and "redirect_link" not in lowered
        and "window.open" not in lowered
    ):
        return None

    try:
        for pattern in JS_REDIRECT_PATTERNS:
            match = pattern.search(content_to_check)
            if not match:
                continue
            candidate = match.group(1).strip()
            if not candidate or candidate.startswith("#") or candidate.lower().startswith("javascript:"):
                continue
            if candidate.startswith(("http://", "https://", "/")):
                joined = urllib.parse.urljoin(base_url, candidate) if base_url else candidate
                cleaned = _clean_extracted_url(joined)
                if _is_followable_http_url(cleaned) and not is_ad_trap(cleaned):
                    return cleaned
    except Exception as exc:
        logger.debug("JS redirect extraction failed: %s", exc)
        return None
    return None



def parse_kmhd_sveltekit_data(html_text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Parse KMHD unlocked SvelteKit payload into (filename, server_links)."""
    name_match = re.search(r'["\']?name["\']?\s*:\s*["\']([^"\']+)["\']', html_text or "")
    file_name = name_match.group(1) if name_match else "Movie.mkv"

    upload_tokens: Dict[str, str] = {}
    upload_match = re.search(r'["\']?upload_links["\']?\s*:\s*\{(.+?)\}', html_text or "", re.DOTALL)
    if upload_match:
        for key, value in re.findall(r'["\']?([a-zA-Z0-9_]+)["\']?\s*:\s*["\']([^"\']+)["\']', upload_match.group(1)):
            if value and value != "None":
                upload_tokens[key] = value

    server_links: List[Tuple[str, str]] = []
    links_match = re.search(r'(?<![a-zA-Z0-9_])["\']?links["\']?\s*:\s*\{(.+?)\}(?:\s*,\s*["\']?ads["\']?:|\s*\}|\s*$)', html_text or "", re.DOTALL)
    if links_match:
        for server_key, base_link in re.findall(
            r'["\']?([a-zA-Z0-9_]+)["\']?\s*:\s*\{[^}]*?["\']?link["\']?\s*:\s*["\']([^"\']+)["\']',
            links_match.group(1),
        ):
            if server_key in upload_tokens:
                full_url = base_link + upload_tokens[server_key]
            else:
                full_url = base_link
            if _is_followable_http_url(full_url):
                label = server_key.replace("_res", "").upper()
                server_links.append((label, full_url))

    if not server_links:
        for match in re.findall(
            r'https?://[^\s"\'<>]+(?:hubcloud|hubdrive|gofile|pixeldrain)[^\s"\'<>]*',
            html_text or "",
            re.I,
        ):
            cleaned = _clean_extracted_url(match)
            if _is_followable_http_url(cleaned) and cleaned not in {item[1] for item in server_links}:
                server_links.append(("MIRROR", cleaned))

    return file_name, server_links


def parse_nextjs_data(html_text: str) -> Optional[dict]:
    """Extract and parse __NEXT_DATA__ JSON script tag from Next.js SSR pages."""
    if not html_text or "__NEXT_DATA__" not in html_text:
        return None
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag and tag.string:
            return json.loads(tag.string)
    except Exception as exc:
        logger.debug("BeautifulSoup failed to parse __NEXT_DATA__: %s", exc)
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception as exc:
            logger.debug("Regex match failed to parse __NEXT_DATA__ JSON: %s", exc)
    return None


def unpack_obfuscator_io_hex_array(script_text: str) -> str:
    """Unpack Obfuscator.io hex string arrays and hex-encoded string literals."""
    if not script_text:
        return script_text

    def _replace_hex(match: re.Match) -> str:
        hex_val = match.group(1)
        try:
            return chr(int(hex_val, 16))
        except Exception:
            return match.group(0)

    decoded = re.sub(r"\\x([0-9a-fA-F]{2})", _replace_hex, script_text)

    def _replace_unicode(match: re.Match) -> str:
        uni_val = match.group(1)
        try:
            return chr(int(uni_val, 16))
        except Exception:
            return match.group(0)

    decoded = re.sub(r"\\u([0-9a-fA-F]{4})", _replace_unicode, decoded)
    return decoded