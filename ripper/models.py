"""
Data models for unshorten-cli (Enterprise & Pro Edition).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ServerMirror:
    """Represents an extracted download server option / mirror from a landing page."""
    label: str
    intermediate_url: str
    direct_download_url: Optional[str] = None
    file_name: str = ""
    file_size_bytes: int = 0
    is_resumable: bool = True
    server_type: str = "Cloud / Direct CDN"
    quality_score: float = 0.0


@dataclass
class HopInfo:
    """Represents a single intermediate hop in a redirect chain."""
    hop_number: int
    url: str
    status_code: int
    redirect_type: str  # e.g. 'HTTP 301', 'HTTP 302', 'Meta Refresh', 'JS Redirect', 'Param Unpack', 'Server Button', 'Final Destination'
    server: str = ""
    content_type: str = ""
    content_length: Optional[int] = None
    latency_ms: float = 0.0
    headers: Dict[str, str] = field(default_factory=dict)
    extra_details: str = ""


@dataclass
class SafetyReport:
    """Security assessment for the resolved final destination URL."""
    domain: str
    is_https: bool
    risk_score: int  # 0 to 100
    risk_level: str  # 'SAFE', 'LOW RISK', 'SUSPICIOUS', 'HIGH RISK'
    mime_category: str  # 'WEBPAGE', 'ARCHIVE', 'EXECUTABLE', 'MEDIA', 'DOCUMENT', 'CLOUD_STORAGE', 'UNKNOWN'
    content_type: str = ""
    content_length_bytes: int = 0
    flags: List[str] = field(default_factory=list)
    ip_address: str = ""


@dataclass
class UnshortenResult:
    """Complete summary result of the unshortening and deep crawl process."""
    original_url: str
    final_url: str
    total_hops: int
    total_time_ms: float
    hops: List[HopInfo]
    safety: SafetyReport
    server_mirrors: List[ServerMirror] = field(default_factory=list)
    is_success: bool = True
    error_message: Optional[str] = None

    @property
    def total_duration_ms(self) -> float:
        """Alias for total_time_ms."""
        return self.total_time_ms

    @property
    def success(self) -> bool:
        """Alias for is_success."""
        return self.is_success

    @property
    def error(self) -> Optional[str]:
        """Alias for error_message."""
        return self.error_message

    @property
    def mirrors(self) -> List[ServerMirror]:
        """Alias for server_mirrors."""
        return self.server_mirrors

    def to_dict(self) -> Dict[str, Any]:

        """Convert result into a serializable dictionary for JSON export."""
        return {
            "original_url": self.original_url,
            "final_url": self.final_url,
            "total_hops": self.total_hops,
            "total_time_ms": round(self.total_time_ms, 2),
            "is_success": self.is_success,
            "error_message": self.error_message,
            "hops": [
                {
                    "hop": h.hop_number,
                    "url": h.url,
                    "status_code": h.status_code,
                    "redirect_type": h.redirect_type,
                    "server": h.server,
                    "content_type": h.content_type,
                    "latency_ms": round(h.latency_ms, 2),
                }
                for h in self.hops
            ],
            "server_mirrors": [
                {
                    "label": m.label,
                    "intermediate_url": m.intermediate_url,
                    "direct_download_url": m.direct_download_url,
                    "file_name": m.file_name,
                    "file_size_bytes": m.file_size_bytes,
                    "is_resumable": m.is_resumable,
                    "server_type": m.server_type,
                }
                for m in self.server_mirrors
            ],
            "safety": {
                "domain": self.safety.domain,
                "is_https": self.safety.is_https,
                "risk_score": self.safety.risk_score,
                "risk_level": self.safety.risk_level,
                "mime_category": self.safety.mime_category,
                "flags": self.safety.flags,
                "content_type": self.safety.content_type,
                "content_length_bytes": self.safety.content_length_bytes,
            },
        }
