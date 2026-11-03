"""
Cryptographic and Obfuscation Unpackers for Ripper Resolver.
Handles Base64, Hex, Rot13, XOR, and query-parameter embedded URLs.
"""
from __future__ import annotations

import base64
import html as html_lib
import logging
import re
import urllib.parse
from typing import Any, Optional, Set

from .honeypot_filter import is_ad_trap

logger = logging.getLogger("ripper.resolver.crypto_unpacker")


QUERY_REDIRECT_KEYS: Set[str] = {
    "url", "dest", "destination", "target", "link", "goto", "to", "r",
    "redirect", "redirect_to", "out", "u", "id", "data", "token", "key",
    "payload", "dl", "file", "download", "href", "src", "path", "down",
}

from .fast_accel import fast_compile

_HEX_URL_RE = fast_compile(r"(?:68747470733a|687474703a)[0-9a-fA-F]{20,}", re.I)
_B64_URL_RE = fast_compile(r"aHR0c[a-zA-Z0-9+/=_\-]{16,}")


def _clean_extracted_url(raw_url: str) -> str:
    """Unescape and strip trailing artifacts from a scraped URL."""
    cleaned = html_lib.unescape((raw_url or "").strip())
    cleaned = cleaned.replace("\\u0026", "&").replace("\\/", "/")
    cleaned = cleaned.replace("&amp;", "&")
    cleaned = cleaned.rstrip(".,;)]}>\"'\\=")
    return cleaned


def _is_followable_http_url(candidate: str) -> bool:
    """True when string is a valid absolute HTTP or HTTPS URL."""
    if not candidate:
        return False
    try:
        parsed = urllib.parse.urlparse(candidate)
        return parsed.scheme.lower() in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def decode_rot13(s: str) -> str:
    """Decode or encode rot13 string."""
    return caesar_decipher(s, shift=13)


def caesar_decipher(s: str, shift: int = 13) -> str:
    """Decipher Caesar/ROT shifted ASCII alphabetic string."""
    if not s:
        return ""
    result = []
    for c in s:
        if 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') - shift + 26) % 26 + ord('a')))
        elif 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') - shift + 26) % 26 + ord('A')))
        else:
            result.append(c)
    return "".join(result)


def decode_multistage_caesar_b64(token_or_url: str, b64_layers: int = 5, caesar_shift: int = 13) -> Optional[str]:
    """
    Decodes multi-layer Base64 + Caesar/ROT13 obfuscated URLs
    (e.g., desbloquea.me, drivelinks.me, enlace-protegido.com /s.php?i=...).
    """
    if not token_or_url:
        return None
    token = token_or_url
    if "/s.php?i=" in token:
        token = token.split("/s.php?i=")[-1]
    elif "?i=" in token:
        token = token.split("?i=")[-1]

    current = token.strip()
    for _ in range(b64_layers):
        try:
            missing = len(current) % 4
            if missing:
                current += "=" * (4 - missing)
            dec = base64.b64decode(current.encode("ascii", errors="ignore")).decode("utf-8", errors="ignore").strip()
            if not dec:
                return None
            current = dec
        except Exception:
            return None

    # Apply Caesar decipher
    final_candidate = caesar_decipher(current, shift=caesar_shift).strip()
    cleaned = _clean_extracted_url(final_candidate)
    if _is_followable_http_url(cleaned):
        return cleaned
    return None


def decode_xor_token(data: str, key: Any) -> str:
    """XOR string decryptor with cycling key, supporting str, int, or bytes keys."""
    if not data or key is None or key == "":
        return data
    if isinstance(key, int):
        key_bytes = bytes([key & 0xFF])
    elif isinstance(key, bytes):
        key_bytes = key
    elif isinstance(key, str):
        key_bytes = key.encode("utf-8")
    else:
        key_bytes = str(key).encode("utf-8")

    if not key_bytes:
        return data
    key_len = len(key_bytes)
    try:
        data_bytes = data.encode("latin-1")
    except Exception:
        data_bytes = data.encode("utf-8", errors="replace")
    dec = bytes([b ^ key_bytes[i % key_len] for i, b in enumerate(data_bytes)])
    try:
        return dec.decode("utf-8")
    except Exception:
        return dec.decode("latin-1", errors="replace")



def decode_base64_url(blob: str) -> Optional[str]:
    """Safely base64 decode a blob, attempting standard and urlsafe alphabets."""
    if not blob:
        return None
    candidate = blob.strip()
    padded = candidate + "=" * ((4 - len(candidate) % 4) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(padded.encode("ascii", errors="ignore"))
            decoded = raw.decode("utf-8", errors="ignore").strip()
            match = re.search(r"https?://[^\s\"'<>]+", decoded)
            if match:
                cleaned = _clean_extracted_url(match.group(0))
                if _is_followable_http_url(cleaned):
                    return cleaned
        except Exception:
            continue
    return None


def extract_url_from_query_params(url: str) -> Optional[str]:
    """Inspect query parameters for embedded/wrapped target URLs or base64 encoded links."""
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        for key, values in params.items():
            if key.lower() not in QUERY_REDIRECT_KEYS:
                continue
            for val in values:
                val_clean = urllib.parse.unquote_plus((val or "").strip())
                if val_clean.startswith("http://") or val_clean.startswith("https://"):
                    cleaned = _clean_extracted_url(val_clean)
                    if _is_followable_http_url(cleaned):
                        return cleaned

                if len(val_clean) >= 12 and not val_clean.startswith("http"):
                    candidates_to_try = [val_clean]
                    if "=" in val_clean:
                        candidates_to_try.append(val_clean.split("=")[0])

                    for candidate in candidates_to_try:
                        decoded_url = decode_base64_url(candidate)
                        if decoded_url and _is_followable_http_url(decoded_url) and not is_ad_trap(decoded_url):
                            return decoded_url
    except Exception:
        return None
    return None


def extract_embedded_b64_url(html_content: str) -> Optional[str]:
    """Scan HTML content for embedded Base64 encoded target URLs."""
    if not html_content or "aHR0c" not in html_content:
        return None

    try:
        matches = _B64_URL_RE.findall(html_content)
        for match_text in matches:
            decoded = decode_base64_url(match_text)
            if decoded and not is_ad_trap(decoded):
                return decoded
    except Exception:
        return None
    return None


def extract_embedded_hex_url(html_content: str) -> Optional[str]:
    """Scan HTML for hex-encoded http(s) URLs."""
    if not html_content:
        return None
    try:
        for raw in _HEX_URL_RE.findall(html_content):
            try:
                decoded = bytes.fromhex(raw).decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if decoded.startswith("http://") or decoded.startswith("https://"):
                cleaned = _clean_extracted_url(decoded)
                if _is_followable_http_url(cleaned) and not is_ad_trap(cleaned):
                    return cleaned
    except Exception:
        return None
    return None


def extract_embedded_encoded_url(html_content: str) -> Optional[str]:
    """Return the first followable URL hidden as base64 or hex in the page."""
    return extract_embedded_b64_url(html_content) or extract_embedded_hex_url(html_content)


def decode_bluemedia_key(encoded: str) -> str:
    """Decode BlueMediaFiles / IGG-Games Create_Button key via bidirectional slicing."""
    if not encoded:
        return ""
    key: list[str] = []
    n = len(encoded)
    i = n // 2 - 5
    while i >= 0:
        key.append(encoded[i])
        i -= 2
    i = n // 2 + 4
    while i < n:
        key.append(encoded[i])
        i += 2
    return "".join(key)


def decode_nested_atob(token: str, max_depth: int = 4) -> Optional[str]:
    """Unwrap multiple layers of atob() (Base64) encoding."""
    if not token:
        return None
    current = token.strip()
    for _ in range(max_depth):
        decoded = decode_base64_url(current)
        if decoded:
            return decoded
        try:
            padded = current + "=" * ((4 - len(current) % 4) % 4)
            raw = base64.b64decode(padded.encode("ascii", errors="ignore")).decode("utf-8", errors="ignore").strip()
            if not raw or raw == current:
                break
            current = raw
            if _is_followable_http_url(current):
                return current
        except Exception:
            break
    return None


def decrypt_adfly_ysmm(ysmm: str) -> Optional[str]:
    """
    Decrypts the Adfly/AdF.ly obfuscated 'ysmm' variable string.
    Alternates characters, XORs digit pairs, and Base64 decodes the inner slice.
    """
    if not ysmm or len(ysmm) < 32:
        return None
    try:
        a: list[str] = []
        b: list[str] = []
        for i in range(len(ysmm)):
            if i % 2 == 0:
                a.append(ysmm[i])
            else:
                b.insert(0, ysmm[i])
        key = list("".join(a) + "".join(b))
        i = 0
        while i < len(key):
            if key[i].isdigit():
                for j in range(i + 1, len(key)):
                    if key[j].isdigit():
                        u = int(key[i]) ^ int(key[j])
                        if u < 10:
                            key[i] = str(u)
                        i = j
                        break
            i += 1
        key_str = "".join(key)
        padded = key_str + "=" * ((4 - len(key_str) % 4) % 4)
        decrypted = base64.b64decode(padded.encode("ascii", errors="ignore"))[16:-16].decode("utf-8", errors="ignore")
        if re.search(r"go\.php\?u=", decrypted):
            decrypted = base64.b64decode(re.sub(r".*?u=", "", decrypted)).decode("utf-8", errors="ignore")
        elif "&dest=" in decrypted:
            decrypted = urllib.parse.unquote(re.sub(r".*?dest=", "", decrypted))
        cleaned = _clean_extracted_url(decrypted)
        if _is_followable_http_url(cleaned):
            return cleaned
    except Exception:
        return None
    return None


def extract_shortener_api_url(url: str) -> Optional[str]:
    """
    Extract destination URL from full-page and quick-link shortener APIs:
    - /full?api={key}&url={base64_encoded_url}
    - /st?api={key}&url={target_url}
    """
    if not url:
        return None
    try:
        m_full = re.search(r"/full\?api=[^&]+&url=([^&]+)", url)
        if m_full:
            raw_val = m_full.group(1)
            decoded = decode_base64_url(raw_val)
            if decoded and _is_followable_http_url(decoded):
                return decoded
            try:
                dec = base64.b64decode(urllib.parse.unquote(raw_val)).decode("utf-8", errors="ignore").strip()
                if _is_followable_http_url(dec):
                    return _clean_extracted_url(dec)
            except Exception as exc:
                logger.debug("Base64 decode attempt failed in extract_shortener_embedded_url: %s", exc)

        m_quick = re.search(r"/st\?api=[^&]+&url=([^&]+)", url)
        if m_quick:
            raw_val = urllib.parse.unquote(m_quick.group(1)).strip()
            cleaned = _clean_extracted_url(raw_val)
            if _is_followable_http_url(cleaned):
                return cleaned
    except Exception as exc:
        logger.debug("Error in extract_shortener_embedded_url: %s", exc)
        return None
    return None


def decode_dealdose_url(url: str) -> Optional[str]:
    """
    Algorithmic unpacker for DealDose / Coupon-based reverse token interstitials.
    Format: https://dealdose.in/verify/{reversed_base64_with_substitutions}
    Cipher: string reversed, '-' -> '+', '_' -> '/', ',' -> '=', then standard Base64 decode.
    """
    if not url or "dealdose.in/verify/" not in url.lower():
        return None
    try:
        m = re.search(r"dealdose\.in/verify/([^/?#&]+)", url, re.I)
        if not m:
            return None
        token = m.group(1).strip()
        # Reverse string and swap URL-safe / comma chars back to standard Base64
        b64_str = token[::-1].replace("-", "+").replace("_", "/").replace(",", "=")
        # Pad if needed
        missing_padding = len(b64_str) % 4
        if missing_padding:
            b64_str += "=" * (4 - missing_padding)
        decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore").strip()
        if _is_followable_http_url(decoded):
            return _clean_extracted_url(decoded)
    except Exception as exc:
        logger.debug("Failed decoding dealdose token: %s", exc)
    return None


def extract_embedded_media_stream(text: str, base_url: str = "") -> Optional[str]:
    """
    Universal heuristic extractor for embedded Master HLS (.m3u8), DASH (.mpd),
    or direct MP4/MKV video stream URLs from scripts, JWPlayer setups, or VideoJS configurations.
    """
    if not text:
        return None

    # 1. JWPlayer / VideoJS sources array: sources: [{file: "..."}] or source: "..."
    jw_match = re.search(r'sources:\s*\[\{[^}]*file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text, re.I)
    if jw_match:
        cand = jw_match.group(1).strip()
        joined = urllib.parse.urljoin(base_url, cand) if base_url else cand
        return _clean_extracted_url(joined)

    # 2. Key-value links: "hls": "...", "file": "...", "src": "..."
    kv_match = re.search(r'["\']?(?:hls|file|video_url|stream_url)["\']?\s*[:=]\s*["\'](https?://[^"\']+\.(?:m3u8|mp4|mkv)[^"\']*)["\']', text, re.I)
    if kv_match:
        return _clean_extracted_url(kv_match.group(1).strip())

    # 3. Bare .m3u8 URLs in script blocks
    bare_m3u8 = re.search(r'["\'](https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)["\']', text, re.I)
    if bare_m3u8:
        return _clean_extracted_url(bare_m3u8.group(1).strip())

    # 4. Bare .mp4 URLs in script blocks
    bare_mp4 = re.search(r'["\'](https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)["\']', text, re.I)
    if bare_mp4:
        cand = bare_mp4.group(1).strip()
        if not is_ad_trap(cand):
            return _clean_extracted_url(cand)

    return None