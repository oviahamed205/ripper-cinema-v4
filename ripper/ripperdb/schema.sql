-- ripperdb Schema Definition v1.0.0
-- High-performance federated search, stream caching, and mirror tracking engine.

PRAGMA foreign_keys = ON;

-- 0. Schema Migrations Tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (1, 'Initial ripperdb schema with FTS5 BM25 and stream cache');

-- 1. Media Entities (Canonical Movies / Shows)
CREATE TABLE IF NOT EXISTS media_entities (
    id TEXT PRIMARY KEY,                       -- e.g. "imdb:tt1375666" or "tmdb:movie:27205" or hash
    imdb_id TEXT,
    tmdb_id TEXT,
    title TEXT NOT NULL,
    clean_title TEXT NOT NULL,
    year INTEGER,
    media_type TEXT NOT NULL CHECK(media_type IN ('movie', 'series', 'anime')),
    poster_url TEXT,
    overview TEXT,
    rating REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_media_entities_clean_title ON media_entities(clean_title);
CREATE INDEX IF NOT EXISTS idx_media_entities_imdb_id ON media_entities(imdb_id);
CREATE INDEX IF NOT EXISTS idx_media_entities_tmdb_id ON media_entities(tmdb_id);

-- 2. Media Providers (Scraped/Crawled from FMHY & Ripper Builtins)
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,                       -- e.g. "cinejoy", "rive", "vegamovies"
    name TEXT NOT NULL,
    archetype TEXT NOT NULL,                   -- 'pstream', 'dooplay', 'embed', 'torrent', 'ddl', 'custom'
    primary_url TEXT NOT NULL,
    section TEXT NOT NULL,                     -- 'streaming', 'ddl', 'torrent', 'anime'
    status TEXT NOT NULL DEFAULT 'active',     -- 'active', 'degraded', 'dead'
    health_score REAL DEFAULT 1.0,
    supports_auto_next INTEGER DEFAULT 0,
    supports_4k INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0.0,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_providers_status ON providers(status);
CREATE INDEX IF NOT EXISTS idx_providers_archetype ON providers(archetype);
CREATE INDEX IF NOT EXISTS idx_providers_section ON providers(section);

-- 3. Domain Mirrors (Active/Backup domains for providers)
CREATE TABLE IF NOT EXISTS domain_mirrors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    mirror_url TEXT NOT NULL,
    mirror_domain TEXT NOT NULL,
    is_primary INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    latency_ms REAL DEFAULT 0.0,
    last_checked_at TIMESTAMP,
    UNIQUE(provider_id, mirror_url)
);

CREATE INDEX IF NOT EXISTS idx_domain_mirrors_domain ON domain_mirrors(mirror_domain);
CREATE INDEX IF NOT EXISTS idx_domain_mirrors_provider ON domain_mirrors(provider_id, is_active);

-- 4. Release Items (Search hits found per provider)
CREATE TABLE IF NOT EXISTS release_items (
    id TEXT PRIMARY KEY,                       -- SHA256(provider_id + item_url)
    media_id TEXT REFERENCES media_entities(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    raw_title TEXT NOT NULL,
    clean_title TEXT NOT NULL,
    item_url TEXT NOT NULL,
    release_year INTEGER,
    resolution TEXT,                          -- '2160p', '1080p', '720p', '480p'
    codec TEXT,                               -- 'HEVC', 'H264', 'AV1'
    audio_channels TEXT,                      -- '5.1', '7.1', '2.0', 'Atmos'
    release_group TEXT,
    quality_score REAL DEFAULT 0.0,
    payload_json TEXT,                        -- provider-specific extra data
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_release_items_media_id ON release_items(media_id);
CREATE INDEX IF NOT EXISTS idx_release_items_provider_id ON release_items(provider_id);
CREATE INDEX IF NOT EXISTS idx_release_items_clean_title ON release_items(clean_title);
CREATE INDEX IF NOT EXISTS idx_release_items_quality ON release_items(quality_score DESC);

-- 5. Stream Cache (Resolved direct stream URLs with TTL)
CREATE TABLE IF NOT EXISTS stream_cache (
    id TEXT PRIMARY KEY,                       -- SHA256(release_item_id + audio/sub_track)
    release_item_id TEXT NOT NULL REFERENCES release_items(id) ON DELETE CASCADE,
    direct_url TEXT NOT NULL,
    headers_json TEXT,                        -- Required Referer, User-Agent, etc.
    quality TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_stream_cache_item ON stream_cache(release_item_id);
CREATE INDEX IF NOT EXISTS idx_stream_cache_expires ON stream_cache(expires_at);

-- 6. FTS5 Virtual Search Table for Lightning-fast Full-Text Queries
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    item_id UNINDEXED,
    raw_title,
    clean_title,
    provider_name,
    release_year UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);

-- 7. Triggers for Automatic search_fts Synchronization
CREATE TRIGGER IF NOT EXISTS trg_release_items_insert AFTER INSERT ON release_items
BEGIN
    INSERT INTO search_fts (item_id, raw_title, clean_title, provider_name, release_year)
    SELECT
        new.id,
        new.raw_title,
        new.clean_title,
        COALESCE((SELECT name FROM providers WHERE id = new.provider_id), new.provider_id),
        CAST(COALESCE(new.release_year, '') AS TEXT);
END;

CREATE TRIGGER IF NOT EXISTS trg_release_items_update AFTER UPDATE ON release_items
BEGIN
    DELETE FROM search_fts WHERE item_id = old.id;
    INSERT INTO search_fts (item_id, raw_title, clean_title, provider_name, release_year)
    SELECT
        new.id,
        new.raw_title,
        new.clean_title,
        COALESCE((SELECT name FROM providers WHERE id = new.provider_id), new.provider_id),
        CAST(COALESCE(new.release_year, '') AS TEXT);
END;

CREATE TRIGGER IF NOT EXISTS trg_release_items_delete AFTER DELETE ON release_items
BEGIN
    DELETE FROM search_fts WHERE item_id = old.id;
END;
