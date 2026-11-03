"""
tests.ripperdb.test_self_healing_phase4
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Comprehensive verification suite for Phase 4: Autonomous Self-Healing Background AI CLI Engine.
Tests heuristic rule matching, local SLM fallback, dead mirror auto-healing,
player fallback cascade, SQLite WAL recovery, FixNet consensus journal,
subprocess interception, and CLI commands.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ripper.cli import main
from ripper.ripperdb.cache import CachedStream, RipperDBCache
from ripper.ripperdb.self_healing import (
    AutonomousHealer,
    FailureCategory,
    FixNetJournal,
    RemediationResult,
    get_autonomous_healer,
    safe_subprocess_run,
)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ripperdb.sqlite"
        db = RipperDBCache(db_path=db_path)
        try:
            yield db
        finally:
            db.close()



@pytest.fixture
def temp_journal():
    with tempfile.TemporaryDirectory() as tmpdir:
        j_path = Path(tmpdir) / "test_journal.json"
        journal = FixNetJournal(journal_path=j_path)
        yield journal


# =============================================================================
# 1. Heuristic Rule Cache & Pattern Matching Tests (<2ms)
# =============================================================================

def test_heuristic_rule_matching_all_categories(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    test_cases = [
        (
            "NameResolutionError: [WinError 11001] getaddrinfo failed for domain vega.movie",
            FailureCategory.DNS_MIRROR_DEAD,
            "DNS_NAME_RESOLUTION_FAILURE",
        ),
        (
            "HTTP Error 403: Forbidden - Attention Required! | Cloudflare cf-chl-bypass",
            FailureCategory.CLOUDFLARE_BLOCKED,
            "CLOUDFLARE_403_429_CHALLENGE",
        ),
        (
            "HTTP Error 401: Unauthorized - SignatureDoesNotMatch on presigned r2.dev stream token",
            FailureCategory.STREAM_TOKEN_EXPIRED,
            "STREAM_URL_TOKEN_EXPIRED_OR_FORBIDDEN",
        ),
        (
            "ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host",
            FailureCategory.CHUNK_TIMEOUT_RESET,
            "CHUNK_SOCKET_RESET_OR_TIMEOUT",
        ),
        (
            "FileNotFoundError: [WinError 2] The system cannot find the file specified: 'C:\\Program Files\\DAUM\\PotPlayer\\PotPlayer64.exe'",
            FailureCategory.PLAYER_CRASH_OR_MISSING,
            "PLAYER_BINARY_MISSING_OR_EXEC_FAIL",
        ),
        (
            "sqlite3.OperationalError: database is locked during WAL checkpoint",
            FailureCategory.DATABASE_CORRUPTION,
            "SQLITE_WAL_LOCK_OR_CORRUPTION",
        ),
        (
            "Zero download items found while parsing media grid selector",
            FailureCategory.PARSER_SELECTOR_BROKEN,
            "DOM_MARKUP_CHANGED_OR_ZERO_ITEMS",
        ),
        (
            "Failed to download subtitle from https://sub.cc/movie.vtt: 404 Not Found",
            FailureCategory.SUBTITLE_FETCH_FAILURE,
            "SUBTITLE_DOWNLOAD_404_OR_ENCODING",
        ),
        (
            "ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            FailureCategory.SSL_CERT_MISMATCH,
            "SSL_CERTIFICATE_VERIFICATION_FAILED",
        ),
        (
            "subprocess.CalledProcessError: Command '['aria2c', '--seed-time=0']' returned non-zero exit status 1",
            FailureCategory.PROCESS_EXIT_ERROR,
            "SUBPROCESS_NON_ZERO_EXIT",
        ),
    ]

    for error_text, expected_cat, expected_rule in test_cases:
        cat, rule, action, desc, tier = healer.diagnose_error(error_text)
        assert cat == expected_cat, f"Expected {expected_cat}, got {cat} for {error_text}"
        assert rule == expected_rule
        assert tier == "HEURISTIC_TIER_0"
        assert len(action) > 0
        assert len(desc) > 0


def test_local_slm_fallback_diagnosis(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)
    novel_error = "QuantumUncertaintyException: Eigenstate flux deviated beyond acceptable threshold at 0x9AF"
    cat, rule, action, desc, tier = healer.diagnose_error(novel_error)
    assert cat == FailureCategory.UNKNOWN_RUNTIME_ANOMALY
    assert tier == "LOCAL_SLM_TIER_1"
    assert "SAFE" in action or "RETRY" in action or "FALLBACK" in action


# =============================================================================
# 2. Dead Mirror Auto-Healing & SQLite Failover Tests
# =============================================================================

def test_dead_mirror_auto_healing(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    # Setup provider with 2 mirrors in temp database
    temp_db.upsert_provider(
        provider_id="test_vega",
        name="VegaMovies Test",
        archetype="dooplay",
        primary_url="https://vegamovies.mex",
    )
    temp_db.upsert_mirror(
        provider_id="test_vega",
        mirror_url="https://vegamovies.mex",
        mirror_domain="vegamovies.mex",
        is_primary=True,
        is_active=True,
        latency_ms=80.0,
    )
    temp_db.upsert_mirror(
        provider_id="test_vega",
        mirror_url="https://vegamovies.yt",
        mirror_domain="vegamovies.yt",
        is_primary=False,
        is_active=True,
        latency_ms=95.0,
    )

    # Mock socket connect so backup mirror succeeds
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock.connect.return_value = None
        mock_sock_cls.return_value = mock_sock

        promoted = healer.heal_dead_mirror("https://vegamovies.mex/movie-123")
        assert promoted == "https://vegamovies.yt"

        # Verify in DB: vegamovies.yt is now primary, vegamovies.mex is inactive
        conn = temp_db._get_connection()
        m_old = conn.execute("SELECT is_active, is_primary FROM domain_mirrors WHERE mirror_domain = 'vegamovies.mex';").fetchone()
        m_new = conn.execute("SELECT is_active, is_primary FROM domain_mirrors WHERE mirror_domain = 'vegamovies.yt';").fetchone()

        assert m_old["is_active"] == 0
        assert m_new["is_primary"] == 1
        assert m_new["is_active"] == 1


# =============================================================================
# 3. Stream Token Refresh & Player Cascade Tests
# =============================================================================

def test_expired_stream_token_recovery(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    # Setup provider and release item for foreign keys
    from ripper.ripperdb.cache import ReleaseItem
    temp_db.upsert_provider(
        provider_id="test_prov",
        name="Test Provider",
        archetype="dooplay",
        primary_url="https://test.prov",
    )
    rel = ReleaseItem(
        id="rel_1",
        provider_id="test_prov",
        raw_title="Interstellar 1080p",
        item_url="https://test.prov/interstellar",
    )
    temp_db.upsert_release_items([rel])

    # Insert a stale stream
    sid = temp_db.set_cached_stream(
        release_item_id="rel_1",
        direct_url="https://cdn.example.com/stream.m3u8?token=expired_tok",
        quality="1080p",
        ttl_seconds=100,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    stale_stream = temp_db.get_cached_stream("rel_1")
    assert stale_stream is not None


    # Mock cascade.resolve to return fresh stream
    fresh = CachedStream(
        id="fresh_stream_456",
        release_item_id="rel_1",
        direct_url="https://cdn.example.com/stream.m3u8?token=fresh_active_token",
        quality="1080p",
        expires_at="2026-09-14T00:00:00Z",
        headers={"User-Agent": "Mozilla/5.0"},
    )

    from unittest.mock import AsyncMock
    with patch("ripper.ripperdb.harvesters.dispatcher.HarvesterDispatcher.resolve_stream", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = fresh
        recovered = healer.refresh_expired_stream(stale_stream, title="Interstellar")

        assert recovered is not None
        assert "fresh_active_token" in recovered.direct_url



def test_player_fallback_cascade(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    # Scenario: PotPlayer failed, MPV is available
    mock_players = [
        ("PotPlayer 64-bit", "C:\\Program Files\\DAUM\\PotPlayer\\PotPlayer64.exe"),
        ("MPV Media Player", "C:\\tools\\mpv\\mpv.exe"),
        ("VLC Media Player", "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"),
    ]

    with patch("ripper.player.detect_available_players", return_value=mock_players), \
         patch("subprocess.Popen") as mock_popen, \
         patch("ripper.player.save_playback_resume_state"):

        mock_popen.return_value = MagicMock()

        ok, msg = healer.heal_player_failure(
            failed_player_name="PotPlayer",
            direct_url="https://fastdl.stream/video.mp4",
            headers={"Referer": "https://fastdl.stream"},
            subtitle_path=None,
            title="Inception",
        )

        assert ok is True
        assert "Stepped down from PotPlayer to MPV" in msg
        # Verify subprocess.Popen was called with MPV binary
        cmd_called = mock_popen.call_args[0][0]
        assert cmd_called[0] == "C:\\tools\\mpv\\mpv.exe"
        assert "--referrer=https://fastdl.stream" in cmd_called


def test_player_fallback_to_system_default(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    # Scenario: No dedicated players installed, fall back to os.startfile
    with patch("ripper.player.detect_available_players", return_value=[]), \
         patch("os.startfile") as mock_startfile, \
         patch("sys.platform", "win32"), \
         patch("ripper.player.save_playback_resume_state"):

        ok, msg = healer.heal_player_failure(
            failed_player_name="PotPlayer",
            direct_url="https://fastdl.stream/video.mp4",
            title="Dune",
        )
        assert ok is True
        assert "Default System Player" in msg
        mock_startfile.assert_called_once_with("https://fastdl.stream/video.mp4")


# =============================================================================
# 4. SQLite Integrity & WAL Recovery Tests
# =============================================================================

def test_database_integrity_and_repair(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)
    rep = healer.heal_database_integrity()
    assert rep["integrity_ok"] is True
    assert rep["wal_checkpoint"] is True
    assert rep["vacuum_applied"] is True


# =============================================================================
# 5. FixNet Cumulative Learning Journal Tests
# =============================================================================

def test_fixnet_journal_persistence(temp_journal):
    temp_journal.record_incident(
        category=FailureCategory.DNS_MIRROR_DEAD,
        rule_name="DNS_NAME_RESOLUTION_FAILURE",
        error_str="WinError 11001",
        action_taken="FAILOVER_ACTIVE_MIRROR",
        success=True,
        duration_ms=4.2,
    )
    temp_journal.record_incident(
        category=FailureCategory.CLOUDFLARE_BLOCKED,
        rule_name="CLOUDFLARE_403_429_CHALLENGE",
        error_str="403 Forbidden cf-chl",
        action_taken="ROTATE_HEADERS_AND_TLS_IMPERSONATION",
        success=True,
        duration_ms=8.5,
    )
    temp_journal.record_incident(
        category=FailureCategory.PLAYER_CRASH_OR_MISSING,
        rule_name="PLAYER_BINARY_MISSING_OR_EXEC_FAIL",
        error_str="PotPlayer missing",
        action_taken="CASCADE_FALLBACK_PLAYER",
        success=False,
        duration_ms=1.1,
    )

    summary = temp_journal.get_summary()
    assert summary["total_intercepted"] == 3
    assert summary["total_auto_healed"] == 2
    assert summary["success_rate_pct"] == 66.7
    assert summary["category_breakdown"]["DNS_MIRROR_DEAD"] == 1
    assert summary["category_breakdown"]["CLOUDFLARE_BLOCKED"] == 1
    assert summary["category_breakdown"]["PLAYER_CRASH_OR_MISSING"] == 1

    # Reload from disk to verify JSON persistence
    reloaded_journal = FixNetJournal(journal_path=temp_journal.path)
    rel_summary = reloaded_journal.get_summary()
    assert rel_summary["total_intercepted"] == 3
    assert rel_summary["total_auto_healed"] == 2

    # Consensus confidence
    conf = temp_journal.get_consensus_confidence(FailureCategory.DNS_MIRROR_DEAD, "FAILOVER_ACTIVE_MIRROR")
    assert conf == 1.0


# =============================================================================
# 6. Subprocess Interception Wrapper Tests
# =============================================================================

def test_safe_subprocess_run_interception(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)

    # 1. Successful command
    res = safe_subprocess_run([sys.executable, "-c", "print('hello')"], healer=healer)
    assert res.returncode == 0
    assert "hello" in res.stdout

    # 2. Command returning non-zero exit code
    res_err = safe_subprocess_run(
        [sys.executable, "-c", "import sys; sys.stderr.write('NameResolutionError: host down\\n'); sys.exit(2)"],
        healer=healer,
    )
    assert res_err.returncode == 2

    # Verify incident recorded in journal
    summary = temp_journal.get_summary()
    assert summary["total_intercepted"] >= 1
    recent = summary["recent_incidents"]
    assert any("DNS" in r.get("rule_name", "") for r in recent)


# =============================================================================
# 7. System Doctor & Full Healing Tests
# =============================================================================

def test_system_doctor_report(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)
    doc_report = healer.run_system_doctor()
    assert "overall_healthy" in doc_report
    checks = doc_report["checks"]
    assert "python_version" in checks
    assert "network" in checks
    assert "media_players" in checks
    assert "database" in checks
    assert "ssl_security" in checks


def test_trigger_full_healing(temp_db, temp_journal):
    healer = AutonomousHealer(db_instance=temp_db, journal=temp_journal)
    res = healer.trigger_full_healing()
    assert res["status"] == "COMPLETED"
    assert "actions_taken" in res
    assert isinstance(res["actions_taken"], list)


# =============================================================================
# 8. CLI Commands (--doctor, --heal, --healer-stats)
# =============================================================================

def test_cli_doctor_command():
    runner = CliRunner()
    result = runner.invoke(main, ["--doctor"])
    assert result.exit_code == 0
    assert "Preflight Diagnostics" in result.output or "System Doctor" in result.output


def test_cli_heal_command():
    runner = CliRunner()
    result = runner.invoke(main, ["--heal"])
    assert result.exit_code == 0
    assert "Autonomous Self-Healing" in result.output or "Self-healing complete" in result.output


def test_cli_healer_stats_command():
    runner = CliRunner()
    result = runner.invoke(main, ["--healer-stats"])
    assert result.exit_code == 0
    assert "FixNet" in result.output or "Autonomy Success Rate" in result.output
