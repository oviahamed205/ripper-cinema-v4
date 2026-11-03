"""
ripper.healer.models
~~~~~~~~~~~~~~~~~~~~

Core dataclasses, state containers, and enums for the autonomous
self-healing scraper subsystem.
"""

from __future__ import annotations

import enum
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..media import MediaDownloadItem


class AnomalyType(str, enum.Enum):
    """Classification of extraction failures and runtime anomalies."""
    ZERO_ITEMS = "zero_items"
    HONEYPOT_DETECTED = "honeypot_detected"
    CLOUDFLARE_BLOCKED = "cloudflare_blocked"
    RATE_LIMITED = "rate_limited"
    CORRUPTED_METADATA = "corrupted_metadata"
    NETWORK_TIMEOUT = "network_timeout"
    UNKNOWN_FAILURE = "unknown_failure"


class HealingStrategy(str, enum.Enum):
    """Strategy tiers used during the self-healing cascade."""
    TIER_0_REGISTRY = "tier_0_registry"
    TIER_1_HEURISTICS = "tier_1_heuristics"
    TIER_2_CAMOUFOX = "tier_2_camoufox"
    TIER_3_FIRECRAWL = "tier_3_firecrawl"
    TIER_4_LOCAL_GGUF = "tier_4_local_gguf"
    TIER_4_CLOUD_LLM = "tier_4_cloud_llm"


@dataclass
class ExtractionAnomaly:
    """Represents a diagnosed anomaly or failure during link extraction."""
    anomaly_type: AnomalyType
    url: str
    status_code: Optional[int] = None
    reason: str = ""
    html_snippet: Optional[str] = None
    extracted_items_count: int = 0
    flagged_urls: List[str] = field(default_factory=list)
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type.value,
            "url": self.url,
            "status_code": self.status_code,
            "reason": self.reason,
            "html_snippet": self.html_snippet[:500] if self.html_snippet else None,
            "extracted_items_count": self.extracted_items_count,
            "flagged_urls": self.flagged_urls,
            "detected_at": self.detected_at,
        }


@dataclass
class HealedResult:
    """Outcome of an autonomous healing session."""
    success: bool
    items: List[MediaDownloadItem] = field(default_factory=list)
    strategy_used: Optional[HealingStrategy] = None
    latency_ms: float = 0.0
    domain_alias: Optional[str] = None
    direct_stream_url: Optional[str] = None
    cached_to_registry: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "items_count": len(self.items),
            "strategy_used": self.strategy_used.value if self.strategy_used else None,
            "latency_ms": round(self.latency_ms, 2),
            "domain_alias": self.domain_alias,
            "direct_stream_url": self.direct_stream_url,
            "cached_to_registry": self.cached_to_registry,
            "details": self.details,
        }


@dataclass
class HealerConfig:
    """Configuration container for the auto-healer subsystem."""
    camoufox_path: str = field(default_factory=lambda: os.environ.get("RIPPER_CAMOUFOX_PATH", "camoufox"))
    local_model_path: str = field(default_factory=lambda: os.environ.get("RIPPER_LOCAL_MODEL_PATH", str(os.path.expanduser("~/.ripper/models/K2-Horizon-1B-BF16.gguf"))))
    firecrawl_api_key: Optional[str] = field(default_factory=lambda: os.environ.get("FIRECRAWL_API_KEY"))
    registry_file: str = "healer_registry.json"
    timeout_fast_path: float = 8.0
    timeout_camoufox: float = 20.0
    timeout_firecrawl: float = 18.0
    timeout_llm: float = 25.0
    headless: bool = True
    enable_registry_cache: bool = True
    enable_auto_promote: bool = True
    max_pruned_dom_bytes: int = 4096

    def __post_init__(self):
        # Resolve Firecrawl key from environment if not explicitly set
        if not self.firecrawl_api_key:
            self.firecrawl_api_key = os.environ.get(
                "FIRECRAWL_API_KEY",
                "fc-1a1447d5a89441fabcc45c9eeee4b45c"
            )
        # Ensure registry directory path is absolute
        if not os.path.isabs(self.registry_file):
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data"
            )
            os.makedirs(data_dir, exist_ok=True)
            self.registry_file = os.path.join(data_dir, self.registry_file)
