"""
Autonomous Input, Domain, and Intent Auto-Detector Package.
Exhaustive recognition of 500+ domains, natural language search parser,
and media player environment discovery.
"""

from .intent import (
    InputIntent,
    ClassifiedExecutionPlan,
    classify_user_input,
    normalize_url,
)
from .title_parser import (
    ParsedQueryIntent,
    parse_query_intent,
)
from .domain_kb import (
    is_known_movie_network,
    is_known_shortener,
    is_direct_cdn,
    is_video_embed_host,
    is_direct_video_file_url,
    extract_root_domain,
)
from .system_probe import (
    DetectedPlayerInfo,
    detect_system_players,
    get_preferred_primary_player,
)

__all__ = [
    "InputIntent",
    "ClassifiedExecutionPlan",
    "classify_user_input",
    "normalize_url",
    "ParsedQueryIntent",
    "parse_query_intent",
    "is_known_movie_network",
    "is_known_shortener",
    "is_direct_cdn",
    "is_video_embed_host",
    "is_direct_video_file_url",
    "extract_root_domain",
    "DetectedPlayerInfo",
    "detect_system_players",
]