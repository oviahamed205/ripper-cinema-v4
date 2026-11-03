"""
ripper.ai_engine
~~~~~~~~~~~~~~~~

Unified local AI intelligence engine for autonomous link extraction,
query understanding, and structured media parsing.
"""

from .models import (
    AIModelStatus,
    AIQueryPlan,
    AIExtractedItem,
    AIExtractionResult,
    AIInferenceConfig,
    BackendType,
)
from .manager import ModelManager
from .runtime import AIEngineRuntime
from .copilot import answer_user_query, display_copilot_response, launch_ai_chat, AICopilotResponse, RIPPER_KNOWLEDGE
from .self_healing import activate_ai_self_healing, auto_heal, WATCHDOG, AISelfHealingWatchdog

_DEFAULT_RUNTIME = None


def get_ai_runtime() -> AIEngineRuntime:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = AIEngineRuntime()
    return _DEFAULT_RUNTIME


def is_ai_ready() -> bool:
    return get_ai_runtime().get_status().is_ready


def get_ai_status() -> AIModelStatus:
    return get_ai_runtime().get_status()


def parse_query_ai(query: str) -> AIQueryPlan:
    return get_ai_runtime().parse_query(query)


async def extract_links_ai(html: str, base_url: str) -> AIExtractionResult:
    return await get_ai_runtime().extract_links(html, base_url)


__all__ = [
    "AIModelStatus",
    "AIQueryPlan",
    "AIExtractedItem",
    "AIExtractionResult",
    "AIInferenceConfig",
    "BackendType",
    "ModelManager",
    "AIEngineRuntime",
    "get_ai_runtime",
    "is_ai_ready",
    "get_ai_status",
    "parse_query_ai",
    "extract_links_ai",
    "answer_user_query",
    "display_copilot_response",
    "launch_ai_chat",
    "AICopilotResponse",
    "RIPPER_KNOWLEDGE",
    "activate_ai_self_healing",
    "auto_heal",
    "WATCHDOG",
    "AISelfHealingWatchdog",
]
