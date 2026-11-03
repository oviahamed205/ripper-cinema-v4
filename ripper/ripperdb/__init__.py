"""
ripper.ripperdb
~~~~~~~~~~~~~~~

Embedded federated search and stream caching engine for ripper.
Provides SQLite WAL persistence, FTS5 BM25 search, stream link TTL caching,
and FMHY live provider mirror synchronization.
"""

from ripper.ripperdb.cache import (
    CachedStream,
    MediaEntity,
    ReleaseItem,
    RipperDBCache,
    estimate_stream_ttl,
    generate_item_id,
    generate_stream_id,
    normalize_title,
)
from ripper.ripperdb.fmhy_sync import (
    FMHYRegistrySync,
    ParsedProvider,
    clean_domain,
    detect_archetype,
)
from ripper.ripperdb.harvesters import (
    BaseHarvester,
    DDLHarvester,
    DooPlayHarvester,
    EmbedHarvester,
    HarvesterDispatcher,
    HarvesterHealth,
    PStreamHarvester,
    TorrentHarvester,
    calculate_quality_score,
)
from ripper.ripperdb.bridge import (
    download_stream,
    format_stream_summary,
    launch_stream_in_player_with_headers,
)
from ripper.ripperdb.self_healing import (
    AutonomousHealer,
    FailureCategory,
    FixNetJournal,
    HeuristicRemediationRule,
    RemediationResult,
    get_autonomous_healer,
    safe_subprocess_run,
)

__all__ = [
    "RipperDBCache",
    "MediaEntity",
    "ReleaseItem",
    "CachedStream",
    "generate_item_id",
    "generate_stream_id",
    "normalize_title",
    "estimate_stream_ttl",
    "FMHYRegistrySync",
    "ParsedProvider",
    "clean_domain",
    "detect_archetype",
    "BaseHarvester",
    "HarvesterHealth",
    "calculate_quality_score",
    "PStreamHarvester",
    "DooPlayHarvester",
    "EmbedHarvester",
    "TorrentHarvester",
    "DDLHarvester",
    "HarvesterDispatcher",
    "launch_stream_in_player_with_headers",
    "download_stream",
    "format_stream_summary",
    "AutonomousHealer",
    "FailureCategory",
    "FixNetJournal",
    "HeuristicRemediationRule",
    "RemediationResult",
    "get_autonomous_healer",
    "safe_subprocess_run",
]

