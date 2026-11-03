"""
ripper.healer
~~~~~~~~~~~~~

Autonomous self-healing extraction subsystem for ripper.
Provides resilient DOM mutation recovery, Camoufox C++ anti-detect stream sniffing,
honeypot defense, Crawl4AI-style DOM pruning, and persistent strategy promotion.
"""

from __future__ import annotations

from .models import (
    AnomalyType,
    ExtractionAnomaly,
    HealedResult,
    HealerConfig,
    HealingStrategy,
)
from .anomaly_detector import AnomalyDetector
from .dynamic_registry import DynamicRegistry
from .dom_pruner import DOMPruner
from .camoufox_sniffer import CamoufoxStreamSniffer
from .llm_dom_diagnostics import LLMDiagnostics
from .orchestrator import AutoHealer, self_healing_extract

__all__ = [
    "AutoHealer",
    "HealerConfig",
    "HealedResult",
    "ExtractionAnomaly",
    "AnomalyType",
    "HealingStrategy",
    "DynamicRegistry",
    "AnomalyDetector",
    "DOMPruner",
    "CamoufoxStreamSniffer",
    "LLMDiagnostics",
    "self_healing_extract",
]
