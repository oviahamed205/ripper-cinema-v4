from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def url_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def safe_url(url: str) -> str:
    """Public diagnostics exclude credentials, path tokens, queries and fragments."""
    try:
        p = urlsplit(url)
        host = p.hostname or "unknown"
        port = f":{p.port}" if p.port else ""
        # Signed tokens can also occur in paths, not only query strings.
        return f"{p.scheme}://{host}{port}/[url:{url_key(url)[:12]}]"
    except ValueError:
        return "[invalid-url]"


@dataclass
class Post:
    url: str
    title: str
    published_at: str | None = None
    discovered_at: str = field(default_factory=utc_now)
    selection_basis: str = "document_order"


@dataclass
class Fetch:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float
    capped: bool

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class Probe:
    status: str  # verified, incomplete, invalid, unreachable, unsupported
    reason: str
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    sample_bitrate_bps: int | None = None
    bytes_sampled: int = 0
    resume_supported: bool | None = None
    sampled_at: str = field(default_factory=utc_now)
    sample_only: bool = True

    @property
    def verified(self) -> bool:
        return self.status == "verified"


@dataclass
class PostResult:
    post: Post
    status: str = "pending"
    reason: str | None = None
    final_url: str | None = None
    probe: Probe | None = None
    attempts: int = 0
    candidate_checks: int = 0
    cache_hits: int = 0
    timings_ms: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0

    def public(self) -> dict[str, Any]:
        d = asdict(self)
        d["post"]["url"] = safe_url(self.post.url)
        if self.final_url:
            d["final_url"] = safe_url(self.final_url)
        return d
