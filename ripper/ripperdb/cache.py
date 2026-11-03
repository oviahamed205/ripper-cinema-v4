"""
ripper.ripperdb.cache
~~~~~~~~~~~~~~~~~~~~~

Production-grade SQLite WAL storage engine for ripperdb.
Handles connection lifecycle, thread safety, full-text FTS5 BM25 search,
stream link caching with TTL eviction, entity resolution, and mirror mapping.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger("ripper.ripperdb.cache")

DEFAULT_DB_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ripper" / "ripperdb.sqlite"

RELEASE_TAGS_RE = re.compile(
    r"\b(?:480p|720p|1080p|1080i|2160p|4k|uhd|fhd|hd|"
    r"bluray|blu-ray|bdrip|brrip|web-dl|webdl|web-rip|webrip|hdrip|dvdrip|dvd|remux|imax|"
    r"x264|x265|h264|h265|hevc|av1|xvid|10bit|8bit|"
    r"aac|ac3|eac3|dts|dts-hd|truehd|atmos|ddp5\.1|5\.1|7\.1|2\.0|"
    r"hdr|hdr10|hdr10\+|dv|dolby\s*vision)\b",
    re.IGNORECASE,
)


def normalize_title(title: str) -> str:
    """Cleans brackets, punctuation, release tags, and extra spaces for matching."""
    if not title:
        return ""
    # Remove bracketed release info like [4K HDR], [HEVC 10bit], etc.
    t = re.sub(r"\[.*?\]", " ", title)
    # Replace parentheses with spaces so '(2010)' becomes ' 2010 '
    t = re.sub(r"[\(\)]", " ", t)
    # Remove common release/scene tags
    t = RELEASE_TAGS_RE.sub(" ", t)
    # Remove special punctuation
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    if not t:
        fallback = re.sub(r"[^\w\s]", " ", title)
        return re.sub(r"\s+", " ", fallback).strip().lower()
    return t


def generate_item_id(provider_id: str, item_url: str) -> str:
    """Generates unique SHA256 identifier for a release item."""
    data = f"{provider_id}:{item_url}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:24]


def generate_stream_id(release_item_id: str, quality: str) -> str:
    """Generates unique SHA256 identifier for cached stream entry."""
    data = f"{release_item_id}:{quality}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:24]


def estimate_stream_ttl(direct_url: str) -> int:
    """
    Computes recommended TTL in seconds:
    - CDN / Tokenized streams (.m3u8, .mp4 with token): 3 hours (10,800s)
    - Embed player URLs (/embed/, /e/, iframe): 24 hours (86,400s)
    - Magnet / Torrent links: 30 days (2,592,000s)
    """
    lowered = direct_url.lower()
    if lowered.startswith("magnet:") or lowered.endswith(".torrent"):
        return 2592000  # 30 days
    if any(tag in lowered for tag in ["/embed/", "/e/", "/v/", "embed", "player"]):
        return 86400  # 24 hours
    return 10800  # 3 hours default for direct CDN streams


@dataclass
class MediaEntity:
    id: str                                    # e.g. "imdb:tt1375666" or "tmdb:movie:27205" or hash
    title: str
    media_type: str                            # 'movie', 'series', 'anime'
    clean_title: str = ""
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    year: Optional[int] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    rating: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.clean_title:
            self.clean_title = normalize_title(self.title)


@dataclass
class ReleaseItem:
    provider_id: str
    raw_title: str
    item_url: str
    clean_title: str = ""
    id: str = ""
    media_id: Optional[str] = None
    release_year: Optional[int] = None
    resolution: Optional[str] = None
    codec: Optional[str] = None
    audio_channels: Optional[str] = None
    release_group: Optional[str] = None
    quality_score: float = 0.0
    payload_json: Optional[str] = None

    def __post_init__(self):
        if not self.clean_title:
            self.clean_title = normalize_title(self.raw_title)
        if not self.id:
            self.id = generate_item_id(self.provider_id, self.item_url)

    @property
    def item_id(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.raw_title

    @property
    def provider(self) -> str:
        return self.provider_id

    @property
    def page_url(self) -> str:
        return self.item_url

    @property
    def quality_tag(self) -> str:
        return self.resolution or "HD"

    @property
    def archetype(self) -> str:
        if self.payload_json:
            try:
                data = json.loads(self.payload_json)
                return data.get("archetype", "custom")
            except Exception:
                pass
        return "custom"

    @property
    def stream_url(self) -> Optional[str]:
        if self.payload_json:
            try:
                data = json.loads(self.payload_json)
                return data.get("stream_url") or data.get("direct_url") or data.get("magnet")
            except Exception:
                pass
        return None

    @property
    def seeders(self) -> Optional[int]:
        if self.payload_json:
            try:
                data = json.loads(self.payload_json)
                return data.get("seeders")
            except Exception:
                pass
        return None

    @property
    def size_bytes(self) -> Optional[int]:
        if self.payload_json:
            try:
                data = json.loads(self.payload_json)
                return data.get("size_bytes")
            except Exception:
                pass
        return None


@dataclass
class CachedStream:
    id: str
    release_item_id: str
    direct_url: str
    quality: str
    expires_at: str
    headers: Dict[str, str] = field(default_factory=dict)
    created_at: Optional[str] = None
    is_direct: bool = True


class RipperDBCache:
    """Thread-safe SQLite engine with WAL mode and FTS5 ranking."""

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._lock = threading.Lock()
        self._schema_file = Path(__file__).parent / "schema.sql"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            db_target = ":memory:" if self.db_path == ":memory:" else str(self.db_path)
            conn = sqlite3.connect(
                db_target,
                timeout=30.0,
                check_same_thread=False,
                isolation_level=None  # autocommit mode
            )
            conn.row_factory = sqlite3.Row
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB mmap
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for atomic multi-statement transactions."""
        conn = self._get_connection()
        with self._lock:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.cursor()
            try:
                yield cursor
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise

    def _init_db(self) -> None:
        """Executes schema creation DDL and tracks migrations."""
        conn = self._get_connection()
        if self._schema_file.exists():
            schema_ddl = self._schema_file.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"Missing schema.sql at {self._schema_file}")

        with self._lock:
            conn.executescript(schema_ddl)
            self._run_migrations(conn)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Applies schema migrations if needed."""
        row = conn.execute("SELECT MAX(version) as max_v FROM schema_migrations;").fetchone()
        current_v = row["max_v"] if row and row["max_v"] is not None else 0
        if current_v < 1:
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (1, 'Initial ripperdb schema');"
            )

    # ---------------------------------------------------------
    # Media Entities (Canonical Movies / TV Shows / Anime)
    # ---------------------------------------------------------

    def upsert_media_entity(self, entity: MediaEntity) -> str:
        """Inserts or updates a canonical media entity."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with self._lock:
            conn.execute(
                """
                INSERT INTO media_entities (
                    id, imdb_id, tmdb_id, title, clean_title, year,
                    media_type, poster_url, overview, rating, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    imdb_id=coalesce(excluded.imdb_id, media_entities.imdb_id),
                    tmdb_id=coalesce(excluded.tmdb_id, media_entities.tmdb_id),
                    title=excluded.title,
                    clean_title=excluded.clean_title,
                    year=coalesce(excluded.year, media_entities.year),
                    media_type=excluded.media_type,
                    poster_url=coalesce(excluded.poster_url, media_entities.poster_url),
                    overview=coalesce(excluded.overview, media_entities.overview),
                    rating=excluded.rating,
                    updated_at=excluded.updated_at;
                """,
                (
                    entity.id,
                    entity.imdb_id,
                    entity.tmdb_id,
                    entity.title,
                    entity.clean_title,
                    entity.year,
                    entity.media_type,
                    entity.poster_url,
                    entity.overview,
                    entity.rating,
                    entity.created_at or now,
                    now,
                ),
            )
        return entity.id

    def get_media_entity(self, entity_id: str) -> Optional[MediaEntity]:
        """Retrieves media entity by its unique ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM media_entities WHERE id = ?;", (entity_id,)).fetchone()
        if not row:
            return None
        return MediaEntity(
            id=row["id"],
            imdb_id=row["imdb_id"],
            tmdb_id=row["tmdb_id"],
            title=row["title"],
            clean_title=row["clean_title"],
            year=row["year"],
            media_type=row["media_type"],
            poster_url=row["poster_url"],
            overview=row["overview"],
            rating=row["rating"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def find_media_entity(
        self,
        title: str,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
        tmdb_id: Optional[str] = None,
    ) -> Optional[MediaEntity]:
        """Finds media entity by IMDb ID, TMDb ID, or normalized clean title and year."""
        conn = self._get_connection()
        if imdb_id:
            row = conn.execute("SELECT * FROM media_entities WHERE imdb_id = ? LIMIT 1;", (imdb_id,)).fetchone()
            if row:
                return self.get_media_entity(row["id"])
        if tmdb_id:
            row = conn.execute("SELECT * FROM media_entities WHERE tmdb_id = ? LIMIT 1;", (tmdb_id,)).fetchone()
            if row:
                return self.get_media_entity(row["id"])

        clean = normalize_title(title)
        query = "SELECT * FROM media_entities WHERE clean_title = ?"
        params: List[Any] = [clean]
        if year:
            query += " AND year = ?"
            params.append(year)
        query += " LIMIT 1;"

        row = conn.execute(query, params).fetchone()
        if row:
            return self.get_media_entity(row["id"])
        return None

    def delete_media_entity(self, entity_id: str) -> bool:
        """Deletes media entity by ID; cascades to dependent release items."""
        conn = self._get_connection()
        with self._lock:
            cur = conn.execute("DELETE FROM media_entities WHERE id = ?;", (entity_id,))
            return cur.rowcount > 0

    # ---------------------------------------------------------
    # Provider & Mirror Management
    # ---------------------------------------------------------

    def upsert_provider(
        self,
        provider_id: str,
        name: str,
        archetype: str,
        primary_url: str,
        section: str = "streaming",
        status: str = "active",
        health_score: float = 1.0,
        supports_auto_next: bool = False,
        supports_4k: bool = False,
        latency_ms: float = 0.0,
    ) -> None:
        """Inserts or updates a media provider record."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with self._lock:
            conn.execute(
                """
                INSERT INTO providers (
                    id, name, archetype, primary_url, section, status,
                    health_score, supports_auto_next, supports_4k, latency_ms, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    archetype=excluded.archetype,
                    primary_url=excluded.primary_url,
                    section=excluded.section,
                    status=excluded.status,
                    health_score=excluded.health_score,
                    supports_auto_next=excluded.supports_auto_next,
                    supports_4k=excluded.supports_4k,
                    latency_ms=excluded.latency_ms,
                    last_synced_at=excluded.last_synced_at;
                """,
                (
                    provider_id,
                    name,
                    archetype,
                    primary_url,
                    section,
                    status,
                    health_score,
                    1 if supports_auto_next else 0,
                    1 if supports_4k else 0,
                    latency_ms,
                    now,
                ),
            )

    def upsert_mirror(
        self,
        provider_id: str,
        mirror_url: str,
        mirror_domain: str,
        is_primary: bool = False,
        is_active: bool = True,
        latency_ms: float = 0.0,
    ) -> None:
        """Registers a mirror URL for a given provider."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with self._lock:
            conn.execute(
                """
                INSERT INTO domain_mirrors (
                    provider_id, mirror_url, mirror_domain, is_primary, is_active, latency_ms, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id, mirror_url) DO UPDATE SET
                    mirror_domain=excluded.mirror_domain,
                    is_primary=excluded.is_primary,
                    is_active=excluded.is_active,
                    latency_ms=excluded.latency_ms,
                    last_checked_at=excluded.last_checked_at;
                """,
                (
                    provider_id,
                    mirror_url,
                    mirror_domain,
                    1 if is_primary else 0,
                    1 if is_active else 0,
                    latency_ms,
                    now,
                ),
            )

    def update_mirror_latency(
        self,
        provider_id: str,
        mirror_url: str,
        latency_ms: float,
        is_active: bool = True,
    ) -> None:
        """Updates measured latency and active status for a mirror."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with self._lock:
            conn.execute(
                """
                UPDATE domain_mirrors
                SET latency_ms = ?, is_active = ?, last_checked_at = ?
                WHERE provider_id = ? AND mirror_url = ?;
                """,
                (latency_ms, 1 if is_active else 0, now, provider_id, mirror_url),
            )

    def get_active_mirror(self, provider_id: str) -> Optional[str]:
        """Returns the lowest-latency active mirror URL for a provider."""
        conn = self._get_connection()
        row = conn.execute(
            """
            SELECT mirror_url FROM domain_mirrors
            WHERE provider_id = ? AND is_active = 1
            ORDER BY is_primary DESC, latency_ms ASC LIMIT 1;
            """,
            (provider_id,),
        ).fetchone()
        return row["mirror_url"] if row else None

    def get_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves provider info along with all active mirrors."""
        conn = self._get_connection()
        p = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if not p:
            return None
        res = dict(p)
        mirrors = conn.execute(
            "SELECT mirror_url, mirror_domain, is_primary, latency_ms FROM domain_mirrors WHERE provider_id = ? AND is_active = 1",
            (provider_id,),
        ).fetchall()
        res["mirrors"] = [dict(m) for m in mirrors]
        return res

    def list_providers(self, section: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """Lists providers optionally filtered by section and status."""
        conn = self._get_connection()
        query = "SELECT * FROM providers WHERE 1=1"
        params: List[Any] = []
        if section:
            query += " AND section = ?"
            params.append(section)
        if active_only:
            query += " AND status = 'active'"
        query += " ORDER BY health_score DESC, name ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------
    # Search & Release Items
    # ---------------------------------------------------------

    def upsert_release_items(self, items: List[ReleaseItem]) -> int:
        """Bulk inserts or updates release items. SQLite triggers automatically update search_fts."""
        if not items:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        inserted_or_updated = 0

        with self.transaction() as cur:
            for item in items:
                cur.execute(
                    """
                    INSERT INTO release_items (
                        id, media_id, provider_id, raw_title, clean_title,
                        item_url, release_year, resolution, codec,
                        audio_channels, release_group, quality_score, payload_json,
                        last_verified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        media_id=coalesce(excluded.media_id, release_items.media_id),
                        raw_title=excluded.raw_title,
                        clean_title=excluded.clean_title,
                        release_year=coalesce(excluded.release_year, release_items.release_year),
                        resolution=coalesce(excluded.resolution, release_items.resolution),
                        codec=coalesce(excluded.codec, release_items.codec),
                        audio_channels=coalesce(excluded.audio_channels, release_items.audio_channels),
                        quality_score=excluded.quality_score,
                        payload_json=excluded.payload_json,
                        last_verified=excluded.last_verified;
                    """,
                    (
                        item.id,
                        item.media_id,
                        item.provider_id,
                        item.raw_title,
                        item.clean_title,
                        item.item_url,
                        item.release_year,
                        item.resolution,
                        item.codec,
                        item.audio_channels,
                        item.release_group,
                        item.quality_score,
                        item.payload_json,
                        now,
                    ),
                )
                inserted_or_updated += 1

        return inserted_or_updated

    def get_release_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a release item by its ID."""
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM release_items WHERE id = ?;", (item_id,)).fetchone()
        return dict(row) if row else None

    def delete_release_item(self, item_id: str) -> bool:
        """Deletes a release item by ID; triggers remove it from search_fts."""
        conn = self._get_connection()
        with self._lock:
            cur = conn.execute("DELETE FROM release_items WHERE id = ?;", (item_id,))
            return cur.rowcount > 0

    def search(
        self,
        query: str,
        limit: int = 50,
        provider_id: Optional[str] = None,
        year: Optional[int] = None,
        min_quality: float = 0.0,
        media_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes lightning-fast FTS5 BM25 search across indexed releases.
        Falls back to LIKE clean_title if FTS query syntax is irregular.
        """
        conn = self._get_connection()
        clean_q = normalize_title(query)
        if not clean_q:
            return []

        # Sanitize query terms: remove FTS5 syntax control chars
        sanitized_terms = [re.sub(r'["*^:\-+\(\)]', '', tok).strip() for tok in clean_q.split()]
        tokens = [f'"{tok}"*' for tok in sanitized_terms if tok]
        if not tokens:
            return []

        fts_match_expr = " AND ".join(tokens)

        sql = """
            SELECT
                r.*,
                p.name as provider_name,
                p.archetype as provider_archetype,
                p.primary_url as provider_primary_url,
                fts.rank as bm25_rank
            FROM search_fts fts
            JOIN release_items r ON fts.item_id = r.id
            JOIN providers p ON r.provider_id = p.id
            WHERE search_fts MATCH ?
        """
        params: List[Any] = [fts_match_expr]

        if provider_id:
            sql += " AND r.provider_id = ?"
            params.append(provider_id)
        if year:
            sql += " AND r.release_year = ?"
            params.append(year)
        if media_id:
            sql += " AND r.media_id = ?"
            params.append(media_id)
        if min_quality > 0.0:
            sql += " AND r.quality_score >= ?"
            params.append(min_quality)

        sql += " ORDER BY bm25_rank ASC, r.quality_score DESC LIMIT ?"
        params.append(limit)

        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            # Fallback to standard LIKE matching if FTS syntax error
            fallback_sql = """
                SELECT
                    r.*,
                    p.name as provider_name,
                    p.archetype as provider_archetype,
                    p.primary_url as provider_primary_url,
                    0.0 as bm25_rank
                FROM release_items r
                JOIN providers p ON r.provider_id = p.id
                WHERE r.clean_title LIKE ?
            """
            f_params: List[Any] = [f"%{clean_q}%"]
            if provider_id:
                fallback_sql += " AND r.provider_id = ?"
                f_params.append(provider_id)
            if year:
                fallback_sql += " AND r.release_year = ?"
                f_params.append(year)
            if media_id:
                fallback_sql += " AND r.media_id = ?"
                f_params.append(media_id)
            if min_quality > 0.0:
                fallback_sql += " AND r.quality_score >= ?"
                f_params.append(min_quality)

            fallback_sql += " ORDER BY r.quality_score DESC LIMIT ?"
            f_params.append(limit)
            rows = conn.execute(fallback_sql, f_params).fetchall()
            return [dict(r) for r in rows]

    # ---------------------------------------------------------
    # Stream Link Cache (TTL-bounded)
    # ---------------------------------------------------------

    def set_cached_stream(
        self,
        release_item_id: str,
        direct_url: str,
        quality: str = "1080p",
        ttl_seconds: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        """Saves a resolved direct media stream link with expiration TTL."""
        if ttl_seconds is None or ttl_seconds <= 0:
            ttl_seconds = estimate_stream_ttl(direct_url)

        stream_id = generate_stream_id(release_item_id, quality)
        now_ts = datetime.now(timezone.utc).timestamp()
        exp_iso = datetime.fromtimestamp(now_ts + ttl_seconds, tz=timezone.utc).isoformat()
        headers_str = json.dumps(headers or {})

        conn = self._get_connection()
        with self._lock:
            conn.execute(
                """
                INSERT INTO stream_cache (
                    id, release_item_id, direct_url, headers_json, quality, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    direct_url=excluded.direct_url,
                    headers_json=excluded.headers_json,
                    expires_at=excluded.expires_at;
                """,
                (stream_id, release_item_id, direct_url, headers_str, quality, exp_iso),
            )
        return stream_id

    def get_cached_stream(self, release_item_id: str, quality: Optional[str] = None) -> Optional[CachedStream]:
        """Retrieves cached stream if not expired; automatically evicts dead records."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()

        sql = """
            SELECT * FROM stream_cache
            WHERE release_item_id = ? AND expires_at > ?
        """
        params: List[Any] = [release_item_id, now_iso]
        if quality:
            sql += " AND quality = ?"
            params.append(quality)
        sql += " ORDER BY quality DESC LIMIT 1;"

        row = conn.execute(sql, params).fetchone()
        if not row:
            return None

        return CachedStream(
            id=row["id"],
            release_item_id=row["release_item_id"],
            direct_url=row["direct_url"],
            quality=row["quality"],
            expires_at=row["expires_at"],
            headers=json.loads(row["headers_json"] or "{}"),
            created_at=row["created_at"],
        )

    def prune_expired_streams(self) -> int:
        """Removes all expired stream cache records."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        with self._lock:
            cur = conn.execute("DELETE FROM stream_cache WHERE expires_at <= ?;", (now_iso,))
            return cur.rowcount

    def evict_expired(self) -> int:
        """Alias for prune_expired_streams."""
        return self.prune_expired_streams()

    def delete_cached_stream(self, stream_id: str) -> bool:
        """Deletes a cached stream entry by ID."""
        conn = self._get_connection()
        with self._lock:
            cur = conn.execute("DELETE FROM stream_cache WHERE id = ?;", (stream_id,))
            return cur.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Returns summary telemetry statistics about providers, mirrors, and cached data."""
        conn = self._get_connection()
        p_count = conn.execute("SELECT COUNT(*) as c FROM providers;").fetchone()["c"]
        m_count = conn.execute("SELECT COUNT(*) as c FROM domain_mirrors;").fetchone()["c"]
        me_count = conn.execute("SELECT COUNT(*) as c FROM media_entities;").fetchone()["c"]
        r_count = conn.execute("SELECT COUNT(*) as c FROM release_items;").fetchone()["c"]
        s_count = conn.execute("SELECT COUNT(*) as c FROM stream_cache;").fetchone()["c"]
        return {
            "db_path": str(self.db_path),
            "providers_count": p_count,
            "mirrors_count": m_count,
            "media_entities_count": me_count,
            "release_items_count": r_count,
            "cached_streams_count": s_count,
        }

    def close(self) -> None:
        """Closes thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


_GLOBAL_DB_INSTANCE: Optional[RipperDBCache] = None
_DB_INSTANCE_LOCK = threading.Lock()


def get_db(db_path: Optional[Path] = None) -> RipperDBCache:
    """Returns singleton RipperDBCache instance."""
    global _GLOBAL_DB_INSTANCE
    with _DB_INSTANCE_LOCK:
        if _GLOBAL_DB_INSTANCE is None:
            _GLOBAL_DB_INSTANCE = RipperDBCache(db_path=db_path)
        return _GLOBAL_DB_INSTANCE


