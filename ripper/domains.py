"""
Live Domain Rotation Radar & Dynamic Mirror Tracker for unshorten-cli.

Prevents dead search engines by tracking dynamic domain migrations & TLD changes.
Persists mirror cache at ~/.ripper/domains.json (override with UNSHORTEN_DOMAINS_FILE).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from .cache import GLOBAL_CACHE
from .media import DEFAULT_HEADERS

_DISK_IO_LOCK = threading.Lock()


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


DOMAINS_CACHE_FILE = Path(
    os.path.expanduser(_env_str("UNSHORTEN_DOMAINS_FILE", str(Path.home() / ".ripper" / "domains.json")))
)
DOMAIN_DISK_TTL = _env_float("UNSHORTEN_DOMAIN_DISK_TTL", 6 * 3600.0)
DOMAIN_MEMORY_TTL = _env_float("UNSHORTEN_DOMAIN_MEMORY_TTL", 86400.0)
PROBE_TIMEOUT = _env_float("UNSHORTEN_DOMAIN_PROBE_TIMEOUT", 3.0)
PROBE_BODY_LIMIT = max(1024, _env_int("UNSHORTEN_DOMAIN_PROBE_BYTES", 8192))

BUILTIN_MIRRORS: Dict[str, str] = {
    "cinefreak": "https://cinefreak.net",
    "kmmovies": "https://kmmovies.pics",
    "katmoviehd": "https://new.katmoviehd.top",
    "katworld": "https://new.katmoviehd.top",
    "vegamovies": "https://new2.vegamovies.futbol",
    "olamovies": "https://v4.olamovies.mov",
    "hdhub4u": "https://hdhub4u.bi",
    "bollyflix": "https://bollyflix.com.in",
    "moviesdrive": "https://moviesdrive.world",
    "moviesmod": "https://moviesmod.vip",
    "uwatchfree": "https://uwatchfree.be",
    # --- New Sites Phase 17 ---
    "fmoviess": "https://fmoviess.org",
    "movie4k": "https://movie4kto.xyz",
    "lookmovie": "https://lookmovie2.city",
    "mp4gana": "https://mp4gana.com",
    "bollypro": "https://bollypro.com",
    "7starhd": "https://7starhd.latino",
    "hindilinks4u": "https://hindilinks4u.estate",
    "worldfree4u": "https://worldfree4u.gd",
    "9xmovie": "https://9xmovielive.com",
    "downloadhub": "https://downloadhub.ac",
    "d8hub": "https://d8.downloadhub.food",
    "movienz": "https://movienz.com",
    "filmsur": "https://filmsur.com",
    "filmshd": "https://filmshd.org",
}

DEFAULT_SITE_DOMAINS: Dict[str, str] = BUILTIN_MIRRORS

KNOWN_FALLBACKS: Dict[str, List[str]] = {
    "cinefreak": ["cinefreak.net", "cinefreak.xyz"],
    "kmmovies": ["kmmovies.pics"],
    "katmoviehd": ["new.katmoviehd.top", "katmoviehd.top", "katmoviehd.nl"],
    "katworld": ["new.katmoviehd.top", "katmoviehd.top", "katmoviehd.nl"],
    "vegamovies": ["new2.vegamovies.futbol", "vegamovies.ph", "vegamovies.yt", "vegamovies.dad", "vegamovies.lol", "vegamovies.nl"],
    "olamovies": ["v4.olamovies.mov", "olamovies.art", "olamovies.homes", "olamovies.lat", "olamovies.top", "olamovies.dad"],
    "hdhub4u": ["hdhub4u.bi", "hdhub4u.lat"],
    "bollyflix": ["bollyflix.com.in", "bollyflix.art"],
    "moviesdrive": ["moviesdrive.world"],
    "moviesmod": ["moviesmod.vip"],
    "uwatchfree": ["uwatchfree.be", "uwatchfree.lat"],
    # --- New Sites Phase 17 ---
    "fmoviess": ["fmoviess.org", "fmoviess.com", "fmoviess.to"],
    "movie4k": ["movie4kto.xyz", "movie4k.to", "movie4k.xyz"],
    "lookmovie": ["lookmovie2.city", "lookmovie2.to", "lookmovie.ag"],
    "mp4gana": ["mp4gana.com", "mp4gana.net"],
    "bollypro": ["bollypro.com", "bollypro.in"],
    "7starhd": ["7starhd.latino", "7starhd.biz", "7starhd.info"],
    "hindilinks4u": ["hindilinks4u.estate", "hindilinks4u.to", "hindilinks4u.net"],
    "worldfree4u": ["worldfree4u.gd", "worldfree4u.com", "worldfree4u.dev"],
    "9xmovie": ["9xmovielive.com", "9xmovie.com", "9xmovies.pro"],
    "downloadhub": ["downloadhub.ac", "downloadhub.foo"],
    "d8hub": ["d8.downloadhub.food", "downloadhub.food"],
    "movienz": ["movienz.com", "movienz.net"],
    "filmsur": ["filmsur.com", "filmsur.net"],
    "filmshd": ["filmshd.org", "filmshd.net"],
}

DISCOVERY_ENDPOINTS: Dict[str, str] = {
    "vegamovies": "https://1vegamovies.cc/?re=vg&t=2",
}

_PARKING_MARKERS = (
    "domain is for sale",
    "buy this domain",
    "parked free",
    "sedo parking",
    "godaddy",
    "this domain has expired",
    "website is for sale",
)


def _now() -> float:
    return time.time()


def _origin_of(url: str) -> str:
    """Return scheme://host for a URL, or empty string if invalid."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    host = parsed.netloc.lower()
    return f"{parsed.scheme}://{host}"


def _as_https_origin(raw: str) -> str:
    """Normalize a host or URL into an https origin when possible."""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return _origin_of(text)
    return _origin_of("https://" + text.lstrip("/"))


def _is_http_origin(url: str) -> bool:
    return bool(_origin_of(url))


def _default_for(site_name: str) -> str:
    key = (site_name or "").lower().strip()
    if key in DEFAULT_SITE_DOMAINS:
        return DEFAULT_SITE_DOMAINS[key]
    fallbacks = KNOWN_FALLBACKS.get(key) or []
    if fallbacks:
        return _as_https_origin(fallbacks[0])
    return f"https://{key}.com"


def _normalize_record(value: Any) -> Optional[Dict[str, Any]]:
    """Accept both legacy 'url' strings and {'url','updated_at'} records."""
    if isinstance(value, str) and _is_http_origin(value):
        return {"url": _origin_of(value), "updated_at": 0.0}
    if isinstance(value, dict):
        url = _origin_of(str(value.get("url") or value.get("domain") or ""))
        if not url:
            return None
        try:
            updated = float(value.get("updated_at") or 0.0)
        except (TypeError, ValueError):
            updated = 0.0
        return {"url": url, "updated_at": updated}
    return None


def _load_local_domain_cache() -> Dict[str, Dict[str, Any]]:
    """Load cached active domains from disk (legacy and timestamped formats)."""
    if not DOMAINS_CACHE_FILE.exists():
        return {
            key: {"url": url, "updated_at": 0.0}
            for key, url in DEFAULT_SITE_DOMAINS.items()
        }

    try:
        with _DISK_IO_LOCK:
            with open(DOMAINS_CACHE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
    except Exception:
        return {
            key: {"url": url, "updated_at": 0.0}
            for key, url in DEFAULT_SITE_DOMAINS.items()
        }

    if not isinstance(data, dict):
        return {
            key: {"url": url, "updated_at": 0.0}
            for key, url in DEFAULT_SITE_DOMAINS.items()
        }

    normalized: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        record = _normalize_record(value)
        if record:
            normalized[str(key).lower()] = record
    for key, url in DEFAULT_SITE_DOMAINS.items():
        normalized.setdefault(key, {"url": url, "updated_at": 0.0})
    return normalized


def _save_local_domain_cache(domains: Dict[str, Dict[str, Any]]) -> None:
    """Atomically save active domains to the disk cache."""
    serializable = {}
    for key, record in domains.items():
        url = _origin_of(str((record or {}).get("url") or ""))
        if not url:
            continue
        try:
            updated = float((record or {}).get("updated_at") or 0.0)
        except (TypeError, ValueError):
            updated = 0.0
        serializable[str(key).lower()] = {"url": url, "updated_at": updated}

    try:
        DOMAINS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(serializable, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(
            prefix="domains.",
            suffix=".tmp",
            dir=str(DOMAINS_CACHE_FILE.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            with _DISK_IO_LOCK:
                os.replace(tmp_name, DOMAINS_CACHE_FILE)
        except Exception:
            try:
                os.unlink(tmp_name)
            except Exception:
                pass
            raise
    except Exception:
        return


def _record_is_fresh(record: Optional[Dict[str, Any]]) -> bool:
    if not record:
        return False
    if not _is_http_origin(str(record.get("url") or "")):
        return False
    try:
        updated = float(record.get("updated_at") or 0.0)
    except (TypeError, ValueError):
        return False
    if updated <= 0:
        return False
    return (time.time() - updated) < DOMAIN_DISK_TTL


def _looks_parked(sample: str) -> bool:
    lowered = (sample or "").lower()
    return any(marker in lowered for marker in _PARKING_MARKERS)


def _status_means_host_live(status_code: int) -> bool:
    """A reachable host serving a real site, challenge wall, or rate limit."""
    if status_code in (401, 403, 429):
        return True
    if 200 <= status_code < 400:
        return True
    return False


async def _probe_origin(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """
    Cheap liveness probe. Prefers HEAD, then a tiny streamed GET.

    Returns the final origin if the host is alive, otherwise None.
    """
    target = _as_https_origin(url) or (url or "").strip()
    if not target:
        return None
    timeout = httpx.Timeout(PROBE_TIMEOUT, connect=min(2.0, PROBE_TIMEOUT))
    headers = dict(DEFAULT_HEADERS or {})

    try:
        head = await client.head(target, headers=headers, timeout=timeout, follow_redirects=True)
        if _status_means_host_live(head.status_code):
            origin = _origin_of(str(head.url)) or _origin_of(target)
            if origin:
                return origin
        if head.status_code in (404, 410, 408) and head.status_code >= 400:
            if head.status_code in (404, 410):
                return None
    except asyncio.CancelledError:
        raise
    except Exception:
        pass

    try:
        if hasattr(client, "stream"):
            async with client.stream(
                "GET", target, headers=headers, timeout=timeout, follow_redirects=True
            ) as response:
                if not _status_means_host_live(response.status_code):
                    return None
                sample = b""
                try:
                    async for chunk in response.aiter_bytes():
                        sample += chunk
                        if len(sample) >= PROBE_BODY_LIMIT:
                            break
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                text_sample = sample.decode("utf-8", errors="ignore")
                if _looks_parked(text_sample):
                    return None
                return _origin_of(str(response.url)) or _origin_of(target)

        response = await client.get(target, headers=headers, timeout=timeout, follow_redirects=True)
        if not _status_means_host_live(response.status_code):
            return None
        body = getattr(response, "text", "") or ""
        if _looks_parked(body[:PROBE_BODY_LIMIT]):
            return None
        return _origin_of(str(response.url)) or _origin_of(target)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


async def discover_vegamovies_domain(client: httpx.AsyncClient) -> str:
    """Probe the VegaMovies CTA redirector for the current live TLD."""
    endpoint = DISCOVERY_ENDPOINTS.get("vegamovies", "https://1vegamovies.cc/?re=vg&t=2")
    timeout = httpx.Timeout(PROBE_TIMEOUT + 1.0, connect=min(2.0, PROBE_TIMEOUT))
    try:
        response = await client.get(
            endpoint,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        origin = _origin_of(str(response.url))
        if origin and "vegamovies" in origin.lower():
            return origin
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    return DEFAULT_SITE_DOMAINS["vegamovies"]


async def probe_fallback_domain(site_name: str, client: httpx.AsyncClient) -> Optional[str]:
    """Probe fallback mirror list concurrently for the first reachable mirror."""
    key = (site_name or "").lower().strip()
    candidates: List[str] = []
    if key == "vegamovies":
        discovered = await discover_vegamovies_domain(client)
        if discovered:
            candidates.append(discovered)
    for item in KNOWN_FALLBACKS.get(key, []):
        origin = _as_https_origin(item)
        if origin and origin not in candidates:
            candidates.append(origin)
    default = _default_for(key)
    if default and default not in candidates:
        candidates.append(default)

    if not candidates:
        return None

    # Probe all candidates concurrently to find the first live one immediately
    tasks = [_probe_origin(client, target) for target in candidates]
    res_list = await asyncio.gather(*tasks, return_exceptions=True)
    for r in res_list:
        if isinstance(r, str) and r:
            return r
    return None


async def get_active_domain(site_name: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """Get active domain for site with memory cache, disk persistence, and live radar."""
    key = (site_name or "").lower().strip()
    if not key:
        return ""

    try:
        cached = await GLOBAL_CACHE.get("domain", key)
        if cached and _is_http_origin(str(cached)):
            return _origin_of(str(cached))
    except asyncio.CancelledError:
        raise
    except Exception:
        pass

    disk_cache = _load_local_domain_cache()
    record = disk_cache.get(key)
    default_val = _default_for(key)
    
    current_val = ""
    if record and _is_http_origin(str(record.get("url") or "")):
        current_val = _origin_of(str(record.get("url")))

    # Verify cached url host is one of the known domains or default
    known_hosts = {urlparse(f).netloc for f in (KNOWN_FALLBACKS.get(key, []) + [default_val]) if f}
    cached_host = urlparse(current_val).netloc if current_val else ""
    if not current_val or (cached_host and cached_host not in known_hosts):
        current_val = default_val
        record = None # Force fresh probe

    if client is not None and not _record_is_fresh(record):
        probed = await _probe_origin(client, current_val)
        if not probed:
            probed = await probe_fallback_domain(key, client)
        if probed:
            current_val = probed
            disk_cache[key] = {"url": current_val, "updated_at": time.time()}
            _save_local_domain_cache(disk_cache)
        elif current_val:
            disk_cache[key] = {"url": current_val, "updated_at": record.get("updated_at", 0.0) if record else 0.0}

    if current_val:
        try:
            await GLOBAL_CACHE.set("domain", key, current_val, ttl=DOMAIN_MEMORY_TTL)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
    return current_val or _default_for(key)

