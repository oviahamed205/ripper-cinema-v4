"""
Unit tests for God-Mode Auto-Pilot modules:
- doh.py
- release_classifier.py
- resilience.py
- health_radar.py
- universal_probe.py
- debrid.py
"""

import pytest
import asyncio
from ripper.doh import resolve_domain_doh, is_doh_enabled, set_doh_enabled
from ripper.release_classifier import classify_release, format_specs_badge
from ripper.resilience import CircuitBreaker
from ripper.health_radar import HealthRadar, MirrorScore
from ripper.universal_probe import unpack_dean_edwards_js
from ripper.debrid import get_saved_debrid_key, save_debrid_key


def test_release_classifier_detailed():
    specs = classify_release("Deadpool.and.Wolverine.2024.IMAX.2160p.UHD.Dolby.Vision.HDR10+.Atmos.x265.REMUX-FLIX")
    assert specs.is_imax is True
    assert specs.resolution == "4K 2160p"
    assert specs.source_tier == "REMUX"
    assert "Dolby Vision" in specs.dynamic_range
    assert specs.audio_codec == "Dolby Atmos"
    assert specs.quality_score >= 90.0

    badge = format_specs_badge(specs)
    assert "4K" in badge
    assert "REMUX" in badge


def test_release_classifier_1080p_webdl():
    specs = classify_release("Spider-Man.No.Way.Home.2021.1080p.WEB-DL.DDP5.1.Atmos.H.264")
    assert specs.resolution == "1080p"
    assert specs.source_tier == "WEB-DL"
    assert specs.audio_codec == "Dolby Atmos"


def test_circuit_breaker_states():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
    host = "test-failing-server.com"

    # Initially healthy
    assert cb.can_request(host) is True

    # 1 failure
    cb.record_failure(host)
    assert cb.can_request(host) is True

    # 2 failures -> Tripped OPEN
    cb.record_failure(host)
    assert cb.can_request(host) is False

    # Success resets
    cb.record_success(host)
    assert cb.can_request(host) is True


def test_health_radar_picker():
    radar = HealthRadar()
    scores = [
        MirrorScore(url="http://slow.com/video.mkv", host="slow.com", latency_ms=850.0, is_alive=True, status_code=200),
        MirrorScore(url="http://fastest.com/video.mkv", host="fastest.com", latency_ms=45.0, is_alive=True, status_code=200),
        MirrorScore(url="http://dead.com/video.mkv", host="dead.com", latency_ms=9999.0, is_alive=False, status_code=500),
    ]
    # Sort: alive first, lowest latency
    sorted_scores = sorted(scores, key=lambda s: (not s.is_alive, s.latency_ms))
    winner = radar.pick_fastest_url(sorted_scores)
    assert winner == "http://fastest.com/video.mkv"


def test_doh_toggle():
    set_doh_enabled(True)
    assert is_doh_enabled() is True
    set_doh_enabled(False)
    assert is_doh_enabled() is False
    set_doh_enabled(True)


def test_universal_probe_packer_unpacker():
    # Test unpacking dean edwards packed string
    packed = unpack_dean_edwards_js("0 1 2", 3, 3, ["foo", "bar", "baz"])
    assert "foo" in packed
    assert "bar" in packed
