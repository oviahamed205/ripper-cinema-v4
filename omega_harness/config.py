from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    mode: str = "first"
    post_limit: int = 5
    site_concurrency: int = 4
    post_concurrency: int = 6
    request_concurrency: int = 8
    per_host_concurrency: int = 2
    candidate_concurrency: int = 2
    candidate_limit: int = 6
    request_timeout: float = 6.0
    post_timeout: float = 12.0
    run_timeout: float = 10.0
    probe_timeout: float = 3.0
    probe_concurrency: int = 2
    max_html_bytes: int = 524288
    max_media_bytes: int = 2097152
    max_playlist_bytes: int = 131072
    redirect_limit: int = 5
    resolve_hops: int = 5
    playlist_depth: int = 3
    retries: int = 1
    cache_seconds: int = 60
    check_resume: bool = False
    allow_private_network: bool = False
    output_dir: str = "omega-output"
    resolver: str = "basic"

    def __post_init__(self):
        if self.mode not in {"first", "audit"}:
            raise ValueError("mode must be first or audit")
        if self.resolver not in {"basic", "ripper"}:
            raise ValueError("resolver must be basic or ripper")
        positive = ("post_limit", "site_concurrency", "post_concurrency", "request_concurrency",
                    "per_host_concurrency", "candidate_concurrency", "candidate_limit",
                    "request_timeout", "post_timeout", "run_timeout", "probe_timeout", "probe_concurrency",
                    "max_html_bytes", "max_media_bytes", "max_playlist_bytes", "resolve_hops", "playlist_depth")
        for name in positive:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_media_bytes < 4096:
            raise ValueError("max_media_bytes must be at least 4096")
        if self.retries < 0 or self.redirect_limit < 0 or self.cache_seconds < 0:
            raise ValueError("retry, redirect and cache limits cannot be negative")
