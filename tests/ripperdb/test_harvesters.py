"""
Tests for ripper.ripperdb.harvesters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Covers:
- BaseHarvester quality scoring and health tracking
- PStreamHarvester JSON API search & stream extraction
- DooPlayHarvester HTML parsing & doo_player_ajax resolution
- EmbedHarvester search & Dean Edwards Packer unpacking
- TorrentHarvester magnet extraction and seeder ranking
- DDLHarvester cyberlocker link resolution
- HarvesterDispatcher federated parallel search & SQLite cache ingestion
- On-demand stream resolution with automatic TTL caching
"""

import asyncio
import json
import pytest
from ripper.ripperdb.cache import (
    CachedStream,
    ReleaseItem,
    RipperDBCache,
    estimate_stream_ttl,
)
from ripper.ripperdb.harvesters.base import (
    BaseHarvester,
    calculate_quality_score,
)
from ripper.ripperdb.harvesters.ddl import DDLHarvester
from ripper.ripperdb.harvesters.dispatcher import HarvesterDispatcher
from ripper.ripperdb.harvesters.dooplay import DooPlayHarvester
from ripper.ripperdb.harvesters.embed import EmbedHarvester
from ripper.ripperdb.harvesters.pstream import PStreamHarvester
from ripper.ripperdb.harvesters.torrent import TorrentHarvester


@pytest.fixture
def cache(tmp_path):
    db_file = tmp_path / "test_harvesters.sqlite"
    engine = RipperDBCache(db_file)
    yield engine
    engine.close()


def test_calculate_quality_score():
    score_4k = calculate_quality_score(resolution="2160p", codec="HEVC", seeders=150)
    score_720p = calculate_quality_score(resolution="720p", codec="x264", seeders=5)
    assert score_4k > score_720p
    assert score_4k >= 90.0
    assert score_720p <= 65.0


@pytest.mark.asyncio
async def test_pstream_search_and_stream(monkeypatch):
    harvester = PStreamHarvester()

    # Mock fetch_json to simulate P-Stream REST API
    sample_api_response = {
        "results": [
            {"id": "mov_101", "title": "Inception", "year": 2010, "resolution": "1080p"},
            {"id": "mov_102", "title": "Interstellar", "year": 2014, "resolution": "2160p"},
        ]
    }

    async def mock_fetch_json(url, headers=None, timeout=None):
        if "api/stream/mov_101" in url:
            return {"stream_url": "https://cdn.pstream.org/hls/mov_101.m3u8"}
        return sample_api_response

    monkeypatch.setattr(harvester, "fetch_json", mock_fetch_json)

    # Test Search
    items = await harvester.search("zstream", "https://zstream.mov", "Inception", year=2010)
    assert len(items) == 1
    assert items[0].raw_title == "Inception (2010)"
    assert items[0].release_year == 2010
    assert items[0].provider_id == "zstream"

    # Test Stream Extraction
    stream = await harvester.extract_stream(items[0], "https://zstream.mov")
    assert stream is not None
    assert stream.direct_url == "https://cdn.pstream.org/hls/mov_101.m3u8"
    assert stream.quality == "1080p"


@pytest.mark.asyncio
async def test_dooplay_search_and_stream(monkeypatch):
    harvester = DooPlayHarvester()

    sample_search_html = """
    <div class="result-item">
        <article class="item-movies post-4521">
            <div class="title"><a href="https://vegamovies.im/inception-2010/">Inception (2010)</a></div>
            <span class="year">2010</span>
            <span class="quality">1080p</span>
        </article>
    </div>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        if "?s=" in url:
            return 200, sample_search_html
        # Detail page with DooPlay player option
        return 200, """
        <ul id="playeroptionsul">
            <li class="dooplay_player_option" data-post="4521" data-nume="1" data-type="movie">Server 1</li>
        </ul>
        """

    async def mock_fetch_json(url, headers=None, timeout=None):
        if "action=doo_player_ajax" in url:
            return {"embed_url": "https://hubcloud.club/drive/stream123"}
        return None

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)
    monkeypatch.setattr(harvester, "fetch_json", mock_fetch_json)

    items = await harvester.search("vegamovies", "https://vegamovies.im", "Inception", year=2010)
    assert len(items) == 1
    assert "Inception" in items[0].raw_title

    stream = await harvester.extract_stream(items[0], "https://vegamovies.im")
    assert stream is not None
    assert "hubcloud.club" in stream.direct_url


@pytest.mark.asyncio
async def test_embed_search_and_packer(monkeypatch):
    harvester = EmbedHarvester()

    sample_search_html = """
    <div class="film_list-wrap">
        <div class="flw-item">
            <a href="https://cinejoy.to/watch/oppenheimer-2023" title="Oppenheimer">
                <div class="film-name">Oppenheimer</div>
            </a>
            <span class="fdi-item">2023</span>
            <span class="fdi-quality">4K</span>
        </div>
    </div>
    """

    # Dean Edwards packed JavaScript snippet hiding .m3u8 source
    packed_js = (
        "<script>eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(new RegExp("
        "'\\\\b'+c+'\\\\b','g'),k[c]);return p}('0.1(\"2://3.4/5.6\");',7,7,"
        "'var|src|https|stream|vidplay|master|m3u8'.split('|'),0,{}))</script>"
    )

    async def mock_fetch_text(url, headers=None, timeout=None):
        if "search" in url:
            return 200, sample_search_html
        return 200, f"<div class='player'>{packed_js}</div>"

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)

    items = await harvester.search("cinejoy", "https://cinejoy.to", "Oppenheimer")
    assert len(items) == 1
    assert items[0].clean_title == "oppenheimer 2023"

    stream = await harvester.extract_stream(items[0], "https://cinejoy.to")
    assert stream is not None
    assert "https://stream.vidplay/master.m3u8" in stream.direct_url


@pytest.mark.asyncio
async def test_torrent_search_and_magnet(monkeypatch):
    harvester = TorrentHarvester()

    sample_1337x_html = """
    <table class="table-list">
        <tbody>
            <tr>
                <td class="name"><a href="/torrent/5001/The-Batman-2022-1080p-BluRay/">The Batman (2022) 1080p BluRay x264</a></td>
                <td class="seeds">1420</td>
                <td class="leeches">310</td>
            </tr>
        </tbody>
    </table>
    """

    sample_detail_html = """
    <div class="torrent-detail">
        <a href="magnet:?xt=urn:btih:b6d92f1a2b3c4d5e&dn=The+Batman">Magnet Download</a>
    </div>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        if "search" in url:
            return 200, sample_1337x_html
        return 200, sample_detail_html

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)

    items = await harvester.search("1337x", "https://1337x.to", "The Batman", year=2022)
    assert len(items) == 1
    assert items[0].resolution == "1080p"
    assert items[0].codec == "X264"
    assert items[0].quality_score > 70.0

    stream = await harvester.extract_stream(items[0], "https://1337x.to")
    assert stream is not None
    assert stream.direct_url.startswith("magnet:?xt=urn:btih:b6d92f1a2b3c4d5e")


@pytest.mark.asyncio
async def test_ddl_search_and_locker(monkeypatch):
    harvester = DDLHarvester()

    sample_ddl_search = """
    <article class="post">
        <h2 class="title"><a href="https://dlhub.in/movie-2025">Gladiator II (2024) Multi 1080p</a></h2>
    </article>
    """

    sample_ddl_detail = """
    <div class="downloads">
        <a href="https://pixeldrain.com/u/abc12345">Download via PixelDrain</a>
    </div>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        if "?s=" in url or "search" in url:
            return 200, sample_ddl_search
        return 200, sample_ddl_detail

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)

    items = await harvester.search("dlhub", "https://dlhub.in", "Gladiator")
    assert len(items) == 1

    stream = await harvester.extract_stream(items[0], "https://dlhub.in")
    assert stream is not None
    assert "pixeldrain.com/api/file/abc12345?download" in stream.direct_url


@pytest.mark.asyncio
async def test_harvester_dispatcher_federated_search_and_resolve(cache, monkeypatch):
    dispatcher = HarvesterDispatcher(cache_engine=cache)

    # Register providers in ripperdb SQLite
    cache.upsert_provider(
        provider_id="prov_pstream",
        name="Test P-Stream",
        archetype="pstream",
        primary_url="https://pstream.test",
        section="streaming",
    )
    cache.upsert_mirror("prov_pstream", "https://pstream.test", "pstream.test", is_primary=True)

    cache.upsert_provider(
        provider_id="prov_embed",
        name="Test Embed",
        archetype="embed",
        primary_url="https://embed.test",
        section="streaming",
    )
    cache.upsert_mirror("prov_embed", "https://embed.test", "embed.test", is_primary=True)

    # Mock search outputs
    async def mock_pstream_search(pid, base, q, year=None):
        return [
            ReleaseItem(
                provider_id=pid,
                raw_title="Interstellar (2014) 1080p",
                item_url="https://pstream.test/watch/101",
                release_year=2014,
                resolution="1080p",
                quality_score=80.0,
            )
        ]

    async def mock_embed_search(pid, base, q, year=None):
        return [
            ReleaseItem(
                provider_id=pid,
                raw_title="Interstellar (2014) 2160p 4K",
                item_url="https://embed.test/watch/202",
                release_year=2014,
                resolution="2160p",
                quality_score=95.0,
            )
        ]

    async def mock_embed_stream(item, base):
        return CachedStream(
            id="stream_test_202",
            release_item_id=item.id,
            direct_url="https://cdn.embed.test/master.m3u8",
            quality="2160p",
            expires_at="",
        )

    monkeypatch.setattr(dispatcher.harvesters["pstream"], "search", mock_pstream_search)
    monkeypatch.setattr(dispatcher.harvesters["embed"], "search", mock_embed_search)
    monkeypatch.setattr(dispatcher.harvesters["embed"], "extract_stream", mock_embed_stream)

    # 1. Execute Federated Search
    results = await dispatcher.federated_search("Interstellar", year=2014, max_providers=5)
    assert len(results) == 2
    # Highest quality score first (embed 2160p 4K with 95.0)
    assert results[0].provider_id == "prov_embed"
    assert results[0].resolution == "2160p"

    # Verify SQLite FTS indexed the hits
    db_hits = cache.search("interstellar")
    assert len(db_hits) == 2

    # 2. Resolve Stream on Demand
    stream = await dispatcher.resolve_stream(results[0].id)
    assert stream is not None
    assert stream.direct_url == "https://cdn.embed.test/master.m3u8"
    assert stream.quality == "2160p"

    # 3. Second call hits SQLite cache fast-path
    cached_fast = await dispatcher.resolve_stream(results[0].id)
    assert cached_fast is not None
    assert cached_fast.id == stream.id


def test_circuit_breaker_health():
    harvester = PStreamHarvester()
    assert harvester.health.is_open is False

    for _ in range(4):
        harvester.record_failure(RuntimeError("Transient error"))
        assert harvester.health.is_open is False

    # 5th failure triggers circuit opening
    harvester.record_failure(RuntimeError("5th consecutive failure"))
    assert harvester.health.is_open is True

    # Success resets circuit breaker
    harvester.record_success(latency_ms=45.0)
    assert harvester.health.is_open is False
    assert harvester.health.consecutive_failures == 0


@pytest.mark.asyncio
async def test_yts_api_search_and_magnet(monkeypatch):
    harvester = TorrentHarvester()

    sample_yts_json = {
        "status": "ok",
        "data": {
            "movies": [
                {
                    "title": "Dune: Part Two",
                    "year": 2024,
                    "slug": "dune-part-two-2024",
                    "torrents": [
                        {
                            "hash": "DUNE2HASH1080P",
                            "quality": "1080p",
                            "type": "bluray",
                            "seeds": 2400,
                            "peers": 450,
                            "size": "2.4 GB",
                        },
                        {
                            "hash": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
                            "quality": "2160p",
                            "type": "x265",
                            "seeds": 1200,
                            "peers": 300,
                            "size": "7.8 GB",
                        },
                    ],
                }
            ]
        },
    }

    async def mock_fetch_json(url, headers=None, timeout=None):
        return sample_yts_json

    monkeypatch.setattr(harvester, "fetch_json", mock_fetch_json)

    items = await harvester.search("yts_mx", "https://yts.mx", "Dune Part Two", year=2024)
    assert len(items) == 2
    assert "2160P" in items[1].raw_title
    assert "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4" in items[1].payload_json

    stream = await harvester.extract_stream(items[1], "https://yts.mx")
    assert stream is not None
    assert stream.direct_url.startswith("magnet:?xt=urn:btih:a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4")
    assert "tracker.opentrackr.org" in stream.direct_url


@pytest.mark.asyncio
async def test_torrentgalaxy_table_search(monkeypatch):
    harvester = TorrentHarvester()

    sample_tgx_html = """
    <div class="tgxtable">
        <div class="tgxtablerow">
            <div class="tgxtablecell">
                <a title="Deadpool & Wolverine 2024 1080p HDR" href="/torrent/8888/Deadpool-Wolverine">Deadpool & Wolverine 2024 1080p HDR</a>
            </div>
            <a href="magnet:?xt=urn:btih:deadpool123hash&dn=Deadpool">Magnet</a>
            <span color="green">3200</span>
        </div>
    </div>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        return 200, sample_tgx_html

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)

    items = await harvester.search("tgx", "https://torrentgalaxy.to", "Deadpool", year=2024)
    assert len(items) == 1
    assert items[0].resolution == "1080p"
    assert "deadpool123hash" in items[0].payload_json


@pytest.mark.asyncio
async def test_torrent_real_debrid_unrestrict(monkeypatch):
    harvester = TorrentHarvester()

    item = ReleaseItem(
        provider_id="yts",
        raw_title="Civil War (2024) 1080p",
        item_url="https://yts.mx/movies/civil-war-2024",
        resolution="1080p",
        payload_json=json.dumps({"magnet": "magnet:?xt=urn:btih:civilwarhash123&dn=Civil+War"}),
    )

    # Mock RealDebridClient
    from ripper.debrid import DebridStreamResult
    async def mock_add_magnet(self, magnet):
        return {"id": "rd_torrent_99"}
    async def mock_select_all_files(self, t_id):
        return True
    async def mock_get_torrent_info(self, t_id):
        return {"links": ["https://real-debrid.com/d/12345"]}
    async def mock_unrestrict_link(self, link):
        return DebridStreamResult(
            stream_url="https://download.real-debrid.com/stream/civil_war_1080p.mp4",
            filename="civil_war_1080p.mp4",
        )

    monkeypatch.setattr("ripper.debrid.get_saved_debrid_key", lambda: "MOCK_RD_KEY_123")
    monkeypatch.setattr("ripper.debrid.RealDebridClient.add_magnet", mock_add_magnet)
    monkeypatch.setattr("ripper.debrid.RealDebridClient.select_all_files", mock_select_all_files)
    monkeypatch.setattr("ripper.debrid.RealDebridClient.get_torrent_info", mock_get_torrent_info)
    monkeypatch.setattr("ripper.debrid.RealDebridClient.unrestrict_link", mock_unrestrict_link)

    stream = await harvester.extract_stream(item, "https://yts.mx")
    assert stream is not None
    assert stream.is_direct is True
    assert "download.real-debrid.com" in stream.direct_url


@pytest.mark.asyncio
async def test_ddl_adgate_and_container_bypassing(monkeypatch):
    harvester = DDLHarvester()

    sample_post_html = """
    <div class="entry-content">
        <a href="https://droplink.co/xyz123">Download via Droplink</a>
        <a href="https://filecrypt.cc/Container/ABCDEF.html">Filecrypt Folder</a>
    </div>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        return 200, sample_post_html

    from ripper.universal_bypasser.models import ShortlinkResult, ContainerResult
    async def mock_bypass(self, url):
        return ShortlinkResult(original_url=url, resolved_url="https://pixeldrain.com/u/directfile77", success=True)
    async def mock_unroll(self, url):
        return ContainerResult(container_url=url, extracted_links=["https://pixeldrain.com/u/directfile77"], success=True)

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)
    monkeypatch.setattr("ripper.universal_bypasser.engine.UniversalBypasserEngine.bypass_shortlink", mock_bypass)
    monkeypatch.setattr("ripper.universal_bypasser.engine.UniversalBypasserEngine.unroll_container", mock_unroll)

    item = ReleaseItem(
        provider_id="ddl_hub",
        raw_title="Alien: Romulus (2024) 1080p",
        item_url="https://ddlhub.org/alien-romulus-2024",
        resolution="1080p",
    )

    stream = await harvester.extract_stream(item, "https://ddlhub.org")
    assert stream is not None
    assert stream.is_direct is True
    assert "pixeldrain.com/api/file/directfile77?download" in stream.direct_url


@pytest.mark.asyncio
async def test_dooplay_wp_rest_api_cascade(monkeypatch):
    harvester = DooPlayHarvester()

    sample_wp_posts = [
        {
            "id": 8801,
            "title": {"rendered": "Gladiator II &#8211; 2024"},
            "link": "https://vegamovies.im/gladiator-2-2024/",
        }
    ]

    async def mock_fetch_json(url, headers=None, timeout=None):
        if "wp-json/wp/v2" in url:
            return sample_wp_posts
        return None

    monkeypatch.setattr(harvester, "fetch_json", mock_fetch_json)

    items = await harvester.search("vegamovies", "https://vegamovies.im", "Gladiator", year=2024)
    assert len(items) == 1
    assert items[0].raw_title == "Gladiator II – 2024"
    assert items[0].release_year == 2024


@pytest.mark.asyncio
async def test_embed_recursive_iframes_and_subtitles(monkeypatch):
    harvester = EmbedHarvester()

    parent_html = """
    <div class="video-container">
        <iframe src="https://embed.server.com/player/sub_iframe"></iframe>
    </div>
    """

    child_html = """
    <video>
        <source src="https://cdn.stream.com/master.m3u8" type="application/x-mpegURL">
        <track kind="subtitles" src="https://cdn.stream.com/subs/en.vtt" srclang="en">
    </video>
    """

    async def mock_fetch_text(url, headers=None, timeout=None):
        if "sub_iframe" in url:
            return 200, child_html
        return 200, parent_html

    monkeypatch.setattr(harvester, "fetch_text", mock_fetch_text)

    item = ReleaseItem(
        provider_id="embed_net",
        raw_title="The Substance 2024",
        item_url="https://embed.net/watch/101",
    )

    stream = await harvester.extract_stream(item, "https://embed.net")
    assert stream is not None
    assert "cdn.stream.com/master.m3u8" in stream.direct_url
    assert "X-Subtitles" in stream.headers
    assert "subs/en.vtt" in stream.headers["X-Subtitles"]


@pytest.mark.asyncio
async def test_dispatcher_advanced_filters_and_fallback(cache, monkeypatch):
    dispatcher = HarvesterDispatcher(cache_engine=cache)

    cache.upsert_provider(
        provider_id="prov_series",
        name="Series Stream",
        archetype="embed",
        primary_url="https://series.test",
        section="tv",
    )
    cache.upsert_mirror("prov_series", "https://series.test", "series.test", is_primary=True)

    # Mock search with quality checking
    async def mock_search(pid, base, q, year=None):
        return [
            ReleaseItem(
                provider_id=pid,
                raw_title="Breaking Bad S01E01 720p",
                item_url="https://series.test/bb-s01e01-720p",
                resolution="720p",
                quality_score=60.0,
            ),
            ReleaseItem(
                provider_id=pid,
                raw_title="Breaking Bad S01E01 1080p",
                item_url="https://series.test/bb-s01e01-1080p",
                resolution="1080p",
                quality_score=85.0,
            ),
        ]

    monkeypatch.setattr(dispatcher.harvesters["embed"], "search", mock_search)

    # Test filtering with min_quality="1080p"
    results = await dispatcher.federated_search(
        "Breaking Bad",
        season=1,
        episode=1,
        min_quality="1080p",
        max_providers=5,
    )
    assert len(results) == 1
    assert results[0].resolution == "1080p"
