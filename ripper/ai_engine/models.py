"""
ripper.ai_engine.models
~~~~~~~~~~~~~~~~~~~~~~~

Data models and type definitions for the local AI inference engine.
Supports K2-Horizon and compatible SLM/LLM architectures.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class BackendType(str, Enum):
    TORCH_GGUF = "torch_gguf"
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    HEURISTIC_FALLBACK = "heuristic_fallback"


@dataclass
class AIModelStatus:
    is_ready: bool
    model_name: str
    model_path: Optional[str] = None
    backend: BackendType = BackendType.HEURISTIC_FALLBACK
    device: str = "cpu"
    file_size_bytes: int = 0
    parameters_billions: float = 1.0
    architecture: str = "k2-horizon"
    loaded_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.loaded_at:
            d["loaded_at"] = self.loaded_at.isoformat()
        d["backend"] = self.backend.value
        return d


@dataclass
class AIInferenceConfig:
    model_path: Optional[str] = None
    max_tokens: int = 512
    temperature: float = 0.1
    top_p: float = 0.95
    device: str = "cpu"
    timeout_seconds: float = 30.0
    use_vulkan: bool = True
    threads: int = 8


@dataclass
class AIQueryPlan:
    """
    Structured execution plan parsed from natural language query.
    """
    raw_query: str
    cleaned_title: str
    media_type: str = "movie"  # "movie", "tv", "stream", "unknown"
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    quality_target: str = "ANY"  # "1080P", "720P", "2160P", "ANY"
    codec_preference: Optional[str] = None  # "X264", "HEVC"
    audio_preference: Optional[str] = None  # "Hindi", "English", "Dual"
    search_keywords: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIQueryPlan":
        return cls(
            raw_query=data.get("raw_query", ""),
            cleaned_title=data.get("cleaned_title", ""),
            media_type=data.get("media_type", "movie"),
            year=data.get("year"),
            season=data.get("season"),
            episode=data.get("episode"),
            quality_target=data.get("quality_target", "ANY"),
            codec_preference=data.get("codec_preference"),
            audio_preference=data.get("audio_preference"),
            search_keywords=data.get("search_keywords", []),
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass
class AIExtractedItem:
    """
    A single media download link parsed from unstructured web content.
    """
    url: str
    movie_name: str
    quality: str = "720P"
    codec: str = "X264"
    size_str: str = "N/A"
    audio_info: str = "Dual Audio"
    confidence: float = 0.95

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIExtractionResult:
    """
    Collection of media items extracted from a web page via local AI.
    """
    source_url: str
    movie_name: str
    items: List[AIExtractedItem] = field(default_factory=list)
    raw_response: str = ""
    backend_used: BackendType = BackendType.HEURISTIC_FALLBACK
    latency_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["backend_used"] = self.backend_used.value
        return d
