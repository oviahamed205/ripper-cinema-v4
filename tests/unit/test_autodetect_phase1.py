"""
Unit Tests for Phase 1: Smart Auto-Detector Engine
"""

import pytest
from ripper.autodetect import (
    InputIntent,
    classify_user_input,
    normalize_url,
    parse_query_intent,
    is_known_movie_network,
    is_known_shortener,
    is_direct_cdn,
    is_video_embed_host,
    is_direct_video_file_url,
    detect_system_players,
)


def test_bare_url_normalization():
    norm = normalize_url("vegamovies.ph/movie-download")
    assert norm == "https://vegamovies.ph/movie-download"

    plan = classify_user_input("vegamovies.ph/movie-download")
    assert plan.intent == InputIntent.URL_MOVIE_PORTAL
    assert plan.normalized_url == "https://vegamovies.ph/movie-download"
    assert "vegamovies" in plan.target_site


def test_direct_stream_urls():
    plan = classify_user_input("https://cdn.pixeldrain.com/api/file/abc12345/video.mkv")
    assert plan.intent == InputIntent.URL_DIRECT_STREAM

    plan2 = classify_user_input("https://omd-rb.workers.dev/serve?t=sample_token")
    assert plan2.intent == InputIntent.URL_DIRECT_STREAM


def test_video_embed_hosts():
    plan = classify_user_input("https://streamwish.to/e/abcdef123456")
    assert plan.intent == InputIntent.URL_VIDEO_HOST

    plan2 = classify_user_input("https://filelions.to/v/xyz987654")
    assert plan2.intent == InputIntent.URL_VIDEO_HOST


def test_shortener_urls():
    plan = classify_user_input("https://ouo.io/s/12345")
    assert plan.intent == InputIntent.URL_SHORTENER

    plan2 = classify_user_input("https://droplink.co/link123")
    assert plan2.intent == InputIntent.URL_SHORTENER


def test_natural_language_movie_search():
    plan = classify_user_input("watch deadpool 2024 in hindi 1080p full movie")
    assert plan.intent == InputIntent.SEARCH_MOVIE
    assert plan.query_specs is not None
    assert plan.query_specs.clean_title.lower() == "deadpool"
    assert plan.query_specs.year == 2024
    assert plan.query_specs.quality_pref == "1080p"
    assert plan.query_specs.audio_pref == "hindi"


def test_tv_series_search():
    plan = classify_user_input("Loki season 2 episode 4 720p")
    assert plan.intent == InputIntent.SEARCH_TV_SERIES
    assert plan.query_specs is not None
    assert plan.query_specs.clean_title.lower() == "loki"
    assert plan.query_specs.season == 2
    assert plan.query_specs.episode == 4
    assert plan.query_specs.is_tv_series is True


def test_html_snippet_detection():
    html = '<div class="download-links"><a href="https://example.com/dl">Direct Download</a></div>'
    plan = classify_user_input(html)
    assert plan.intent == InputIntent.HTML_SNIPPET


def test_empty_input_dashboard_launch():
    plan = classify_user_input("")
    assert plan.intent == InputIntent.DASHBOARD

    plan2 = classify_user_input("   ")
    assert plan2.intent == InputIntent.DASHBOARD


def test_system_player_discovery():
    players = detect_system_players()
    assert isinstance(players, list)
