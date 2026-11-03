"""
Tests for ripper.ripperdb.cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Covers:
- Database initialization and schema creation
- Provider & Mirror CRUD operations
- Release items ingestion and FTS5 BM25 search
- Title normalization and ID generation
- Stream cache lifecycle, TTL expiration, and pruning
- Multi-threading concurrency safety
"""

import threading
import time
from datetime import datetime, timezone
import pytest
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


@pytest.fixture
def cache(tmp_path):
    db_file = tmp_path / "test_ripperdb.sqlite"
    engine = RipperDBCache(db_file)
    yield engine
    engine.close()


def test_normalize_title():
    raw = "[4K HDR] Inception (2010) [HEVC 10bit] [5.1 Audio]!"
    cleaned = normalize_title(raw)
    assert cleaned == "inception 2010"


def test_provider_and_mirror_lifecycle(cache):
    cache.upsert_provider(
        provider_id="cinejoy",
        name="Cinejoy",
        archetype="embed",
        primary_url="https://cinejoy.to",
        section="streaming",
        supports_auto_next=True,
        supports_4k=True,
        health_score=0.95,
    )

    cache.upsert_mirror(
        provider_id="cinejoy",
        mirror_url="https://cinejoy.to",
        mirror_domain="cinejoy.to",
        is_primary=True,
        is_active=True,
        latency_ms=80.0,
    )

    cache.upsert_mirror(
        provider_id="cinejoy",
        mirror_url="https://cinejoy.is",
        mirror_domain="cinejoy.is",
        is_primary=False,
        is_active=True,
        latency_ms=45.0,
    )

    provider = cache.get_provider("cinejoy")
    assert provider is not None
    assert provider["name"] == "Cinejoy"
    assert provider["supports_4k"] == 1
    assert len(provider["mirrors"]) == 2

    # Cinejoy primary is active
    active = cache.get_active_mirror("cinejoy")
    assert active in ("https://cinejoy.to", "https://cinejoy.is")

    providers = cache.list_providers(section="streaming")
    assert len(providers) == 1
    assert providers[0]["id"] == "cinejoy"


def test_release_items_and_fts_search(cache):
    cache.upsert_provider(
        provider_id="rive",
        name="Rive Stream",
        archetype="embed",
        primary_url="https://rivestream.app",
        section="streaming",
    )

    items = [
        ReleaseItem(
            provider_id="rive",
            raw_title="Interstellar (2014) IMAX 1080p BluRay",
            item_url="https://rivestream.app/watch/interstellar-2014",
            release_year=2014,
            resolution="1080p",
            codec="H264",
            quality_score=85.0,
        ),
        ReleaseItem(
            provider_id="rive",
            raw_title="Inception (2010) [2160p 4K UHD Remux]",
            item_url="https://rivestream.app/watch/inception-2010",
            release_year=2010,
            resolution="2160p",
            codec="HEVC",
            quality_score=98.0,
        ),
        ReleaseItem(
            provider_id="rive",
            raw_title="The Dark Knight (2008) 720p WEB-DL",
            item_url="https://rivestream.app/watch/the-dark-knight-2008",
            release_year=2008,
            resolution="720p",
            codec="H264",
            quality_score=60.0,
        ),
    ]

    count = cache.upsert_release_items(items)
    assert count == 3

    # Search for Inception
    results = cache.search("inception")
    assert len(results) == 1
    assert results[0]["clean_title"] == "inception 2010"
    assert results[0]["resolution"] == "2160p"
    assert results[0]["provider_name"] == "Rive Stream"

    # Search with year filter
    results_year = cache.search("interstellar", year=2014)
    assert len(results_year) == 1
    assert results_year[0]["clean_title"] == "interstellar 2014"

    # Search empty query
    assert cache.search("") == []


def test_stream_cache_ttl_and_pruning(cache):
    # Set up provider and parent release_item to satisfy foreign keys
    cache.upsert_provider(
        provider_id="rive",
        name="Rive Stream",
        archetype="embed",
        primary_url="https://rivestream.app",
    )
    parent_item = ReleaseItem(
        provider_id="rive",
        raw_title="Test Stream Movie (2025)",
        item_url="https://rivestream.app/watch/test-stream-2025",
        id="test_item_123",
    )
    cache.upsert_release_items([parent_item])

    item_id = "test_item_123"
    stream_id = cache.set_cached_stream(
        release_item_id=item_id,
        direct_url="https://cdn.example.com/stream.m3u8",
        quality="1080p",
        ttl_seconds=1,  # 1 second TTL for test
        headers={"User-Agent": "Mozilla/5.0"},
    )
    assert stream_id is not None

    # Immediate retrieval should succeed
    cached = cache.get_cached_stream(item_id, quality="1080p")
    assert cached is not None
    assert cached.direct_url == "https://cdn.example.com/stream.m3u8"
    assert cached.headers["User-Agent"] == "Mozilla/5.0"

    # Sleep 1.2s to exceed TTL
    time.sleep(1.2)

    # Retrieval after expiration returns None
    assert cache.get_cached_stream(item_id, quality="1080p") is None

    # Prune expired items
    deleted = cache.prune_expired_streams()
    assert deleted >= 1


def test_concurrent_writes(cache):
    cache.upsert_provider(
        provider_id="concurrent_prov",
        name="Concurrent Test",
        archetype="custom",
        primary_url="https://test.com",
    )

    def worker(worker_id):
        items = [
            ReleaseItem(
                provider_id="concurrent_prov",
                raw_title=f"Movie {worker_id}-{i} (2025)",
                item_url=f"https://test.com/{worker_id}/{i}",
                release_year=2025,
            )
            for i in range(10)
        ]
        cache.upsert_release_items(items)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # We inserted 5 threads * 10 items = 50 items
    hits = cache.search("movie")
    assert len(hits) == 50


def test_media_entity_crud_and_cascade(cache):
    # Create canonical media entity
    entity = MediaEntity(
        id="imdb:tt1375666",
        imdb_id="tt1375666",
        tmdb_id="27205",
        title="Inception",
        year=2010,
        media_type="movie",
        rating=8.8,
        overview="A thief who steals corporate secrets through the use of dream-sharing technology...",
    )
    e_id = cache.upsert_media_entity(entity)
    assert e_id == "imdb:tt1375666"

    # Retrieve by ID
    retrieved = cache.get_media_entity("imdb:tt1375666")
    assert retrieved is not None
    assert retrieved.title == "Inception"
    assert retrieved.clean_title == "inception"
    assert retrieved.rating == 8.8

    # Lookup by IMDB ID
    found_imdb = cache.find_media_entity(title="Anything", imdb_id="tt1375666")
    assert found_imdb is not None
    assert found_imdb.id == "imdb:tt1375666"

    # Lookup by TMDb ID
    found_tmdb = cache.find_media_entity(title="Anything", tmdb_id="27205")
    assert found_tmdb is not None
    assert found_tmdb.id == "imdb:tt1375666"

    # Lookup by clean title and year
    found_title = cache.find_media_entity(title="Inception", year=2010)
    assert found_title is not None
    assert found_title.id == "imdb:tt1375666"

    # Create provider and child release item linked to media_id
    cache.upsert_provider("p_cascade", "Cascade Provider", "embed", "https://cascade.com")
    item = ReleaseItem(
        id="item_cascade_1",
        media_id="imdb:tt1375666",
        provider_id="p_cascade",
        raw_title="Inception (2010) 1080p BluRay",
        item_url="https://cascade.com/watch/1",
    )
    cache.upsert_release_items([item])
    assert cache.get_release_item("item_cascade_1") is not None

    # Delete media entity; verify ON DELETE CASCADE removes linked release item
    deleted = cache.delete_media_entity("imdb:tt1375666")
    assert deleted is True
    assert cache.get_media_entity("imdb:tt1375666") is None
    assert cache.get_release_item("item_cascade_1") is None


def test_stream_ttl_auto_detection(cache):
    assert estimate_stream_ttl("https://cdn.example.com/playlist.m3u8?token=xyz") == 10800  # 3 hours
    assert estimate_stream_ttl("https://streamer.com/embed/xyz123") == 86400  # 24 hours
    assert estimate_stream_ttl("magnet:?xt=urn:btih:abcdef123456") == 2592000  # 30 days
    assert estimate_stream_ttl("https://torrents.com/file.torrent") == 2592000

    cache.upsert_provider("ttl_prov", "TTL Prov", "embed", "https://ttl.com")
    cache.upsert_release_items([
        ReleaseItem(id="item_ttl_1", provider_id="ttl_prov", raw_title="Test TTL", item_url="https://ttl.com/1")
    ])

    # Auto-detection for embed link
    sid = cache.set_cached_stream("item_ttl_1", "https://ttl.com/embed/player1", quality="1080p")
    cached = cache.get_cached_stream("item_ttl_1", quality="1080p")
    assert cached is not None
    assert cached.direct_url == "https://ttl.com/embed/player1"

    # Test delete cached stream
    deleted = cache.delete_cached_stream(sid)
    assert deleted is True
    assert cache.get_cached_stream("item_ttl_1", quality="1080p") is None


def test_sqlite_triggers_fts_sync(cache):
    cache.upsert_provider("prov_trg", "Trigger Provider", "embed", "https://trg.com")

    # 1. Insert item
    item = ReleaseItem(
        id="item_trg_1",
        provider_id="prov_trg",
        raw_title="Gladiator (2000) Remastered 1080p",
        item_url="https://trg.com/gladiator",
        release_year=2000,
    )
    cache.upsert_release_items([item])

    results = cache.search("gladiator")
    assert len(results) == 1
    assert results[0]["id"] == "item_trg_1"

    # 2. Update item
    item_upd = ReleaseItem(
        id="item_trg_1",
        provider_id="prov_trg",
        raw_title="Gladiator II (2024) 4K UHD",
        item_url="https://trg.com/gladiator",
        release_year=2024,
    )
    cache.upsert_release_items([item_upd])

    results_old = cache.search("gladiator 2000")
    assert len(results_old) == 0
    results_new = cache.search("gladiator 2024")
    assert len(results_new) == 1

    # 3. Delete item; trigger removes from search_fts
    cache.delete_release_item("item_trg_1")
    assert len(cache.search("gladiator")) == 0


def test_mirror_latency_update(cache):
    cache.upsert_provider("lat_prov", "Latency Prov", "embed", "https://lat1.com")
    cache.upsert_mirror("lat_prov", "https://lat1.com", "lat1.com", is_primary=True, latency_ms=100.0)
    cache.upsert_mirror("lat_prov", "https://lat2.com", "lat2.com", is_primary=False, latency_ms=200.0)

    # Initially lat1 has 100ms, lat2 has 200ms
    assert cache.get_active_mirror("lat_prov") == "https://lat1.com"

    # Update lat2 to be faster (30ms) and lat1 to be slower (500ms)
    cache.update_mirror_latency("lat_prov", "https://lat1.com", latency_ms=500.0)
    cache.update_mirror_latency("lat_prov", "https://lat2.com", latency_ms=30.0)

    # Order is by is_primary DESC, latency_ms ASC; if lat1 is primary, it still takes precedence unless disabled
    cache.update_mirror_latency("lat_prov", "https://lat1.com", latency_ms=500.0, is_active=False)
    # Now lat1 is inactive, lat2 is active
    assert cache.get_active_mirror("lat_prov") == "https://lat2.com"


def test_sql_injection_safety(cache):
    cache.upsert_provider("safe_prov", "Safe Prov", "embed", "https://safe.com")
    cache.upsert_release_items([
        ReleaseItem(
            id="safe_item_1",
            provider_id="safe_prov",
            raw_title="The Matrix (1999) 1080p",
            item_url="https://safe.com/matrix",
        )
    ])

    # Adversarial search queries must never crash or execute injected SQL
    adversarial_queries = [
        "' OR '1'='1",
        "'; DROP TABLE release_items; --",
        "Matrix' AND 1=1 --",
        '"""***:::^^^---+++',
        "SELECT * FROM providers",
        "' UNION SELECT NULL, NULL, NULL --",
    ]
    for q in adversarial_queries:
        res = cache.search(q)
        assert isinstance(res, list)

    # Release items table must still exist and have data
    assert cache.get_release_item("safe_item_1") is not None


def test_search_performance_sub_25ms(cache):
    """Verifies that search queries execute well within the sub-25ms SLA."""
    cache.upsert_provider("perf_prov", "Performance Provider", "embed", "https://perf.com")

    # Ingest 200 release items
    items = [
        ReleaseItem(
            provider_id="perf_prov",
            raw_title=f"Action Blockbuster Volume {i} (202{i % 5}) [1080p BluRay]",
            item_url=f"https://perf.com/watch/{i}",
            release_year=2020 + (i % 5),
            quality_score=float(i % 100),
        )
        for i in range(200)
    ]
    cache.upsert_release_items(items)

    # Execute 50 search iterations and measure latency
    latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        hits = cache.search("action blockbuster", limit=20)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)
        assert len(hits) > 0

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    # Must be strictly under 25ms SLA (typically < 3ms with SQLite FTS5 WAL)
    assert avg_latency < 25.0, f"Average latency {avg_latency:.2f}ms exceeded 25ms SLA"
    assert max_latency < 50.0, f"Max latency {max_latency:.2f}ms was unusually high"

