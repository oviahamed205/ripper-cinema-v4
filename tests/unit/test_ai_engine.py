"""
Unit tests for ripper.ai_engine:
K2-Horizon model discovery, GBNF grammar parsing, prompt formatting,
PyTorch GGUF runtime, query planning, and DOM link extraction.
"""

import pytest
import asyncio
from ripper.ai_engine import (
    AIEngineRuntime,
    AIExtractedItem,
    AIExtractionResult,
    AIModelStatus,
    AIQueryPlan,
    BackendType,
    get_ai_runtime,
    get_ai_status,
    is_ai_ready,
    parse_query_ai,
    extract_links_ai,
)
from ripper.ai_engine.grammar import clean_json_markdown, parse_strict_json, GBNF_LINK_EXTRACTION, GBNF_QUERY_PARSING
from ripper.ai_engine.prompts import build_chatml_prompt, MEDIA_EXTRACTION_SYSTEM
from ripper.ai_engine.manager import ModelManager
from ripper.autodetect.intent import classify_user_input, InputIntent
from ripper.universal_engine.llm_extractor import LLMStructuralExtractor


def test_ai_status_and_discovery():
    status = get_ai_status()
    assert isinstance(status, AIModelStatus)
    assert status.is_ready is True
    assert status.model_name in ("K2-Horizon-1B", "DeterministicHeuristicEngine")
    assert status.backend in (BackendType.TORCH_GGUF, BackendType.HEURISTIC_FALLBACK)
    assert status.file_size_bytes >= 0
    d = status.to_dict()
    assert "model_name" in d
    assert "backend" in d


def test_ai_models_serialization():
    plan = AIQueryPlan(
        raw_query="avatar 2 2022 1080p",
        cleaned_title="avatar 2",
        media_type="movie",
        year=2022,
        quality_target="1080P",
        confidence=0.95,
    )
    d = plan.to_dict()
    assert d["year"] == 2022
    assert d["cleaned_title"] == "avatar 2"
    reconstructed = AIQueryPlan.from_dict(d)
    assert reconstructed.cleaned_title == "avatar 2"
    assert reconstructed.year == 2022

    item = AIExtractedItem(
        url="https://cloud.direct/file.mkv",
        movie_name="Avatar",
        quality="1080P",
        codec="HEVC",
        size_str="2.5GB",
    )
    assert item.to_dict()["size_str"] == "2.5GB"


def test_grammar_json_parsing_and_markdown_stripping():
    assert "root ::=" in GBNF_LINK_EXTRACTION
    assert "root ::=" in GBNF_QUERY_PARSING

    # Normal JSON
    assert parse_strict_json('{"key": "val"}') == {"key": "val"}

    # Markdown fence wrapped JSON
    fenced = "```json\n{\"movie_name\": \"Dune\", \"items\": []}\n```"
    parsed = parse_strict_json(fenced)
    assert parsed.get("movie_name") == "Dune"

    # Conversational lead-in
    conversational = "Here is your requested JSON response:\n{\"status\": \"success\"} Hope this helps!"
    parsed_conv = parse_strict_json(conversational)
    assert parsed_conv.get("status") == "success"

    # Malformed fallback
    assert parse_strict_json("Not a json at all", default={"fallback": True}) == {"fallback": True}


def test_chatml_prompt_builder():
    prompt = build_chatml_prompt(MEDIA_EXTRACTION_SYSTEM, "Extract links from example.com")
    assert "<|im_start|>system" in prompt
    assert "<|im_end|>" in prompt
    assert "<|im_start|>user" in prompt
    assert "<|im_start|>assistant" in prompt


def test_query_planner_tv_series():
    plan = parse_query_ai("Breaking Bad S04E07 1080p hevc dual audio")
    assert plan.media_type == "tv"
    assert plan.season == 4
    assert plan.episode == 7
    assert plan.quality_target == "1080P"
    assert plan.codec_preference == "HEVC"
    assert plan.audio_preference == "Dual Audio"
    assert "breaking" in plan.search_keywords


def test_query_planner_movie():
    plan = parse_query_ai("Oppenheimer 2023 2160p 4K remux hindi")
    assert plan.media_type == "movie"
    assert plan.year == 2023
    assert plan.quality_target == "2160P"
    assert plan.codec_preference == "REMUX"
    assert plan.audio_preference == "Dual Audio"


@pytest.mark.anyio
async def test_ai_link_extraction_html():
    sample_html = """
    <html>
        <body>
            <h1>Inception (2010)</h1>
            <div class="download-section">
                <a href="https://fastcloud.download/file_1080p_hevc.mkv">Download 1080p HEVC [2.4GB] Dual Audio</a>
                <a href="https://fastcloud.download/file_720p_x264.mkv">Download 720p x264 [1.1GB] Dual Audio</a>
                <a href="https://external.ads/click">Ad Click</a>
            </div>
        </body>
    </html>
    """
    res = await extract_links_ai(sample_html, "https://movies.test/inception")
    assert isinstance(res, AIExtractionResult)
    assert len(res.items) >= 2
    qualities = [it.quality for it in res.items]
    assert "1080P" in qualities
    assert "720P" in qualities
    assert all("fastcloud.download" in it.url for it in res.items)


@pytest.mark.anyio
async def test_universal_llm_extractor_fallback():
    # When api_key is None, LLMStructuralExtractor uses local ai_engine
    extractor = LLMStructuralExtractor(api_key=None)
    sample_html = """
    <html>
        <h1>Interstellar</h1>
        <a href="https://drive.mega.stream/interstellar_1080p.mkv">Watch 1080p HEVC Dual Audio 3.2GB</a>
    </html>
    """
    items = await extractor.extract_items(sample_html, "https://streams.test/interstellar")
    assert len(items) >= 1
    assert items[0].quality == "1080P"
    assert items[0].movie_name == "Interstellar"
    assert "drive.mega.stream" in items[0].short_link


def test_autodetect_intent_with_ai():
    plan = classify_user_input("Download Gladiator 2 2024 1080p")
    assert plan.intent == InputIntent.SEARCH_MOVIE
    assert plan.ai_plan is not None
    assert plan.ai_plan.year == 2024
    assert plan.ai_plan.quality_target == "1080P"


def test_ai_copilot_capabilities():
    from ripper.ai_engine import answer_user_query
    resp = answer_user_query("what can you do?")
    assert "K2-Horizon 1B" in resp.answer
    assert "1-Click Instant Watch" in resp.answer
    assert resp.action_type == "help"


def test_ai_copilot_bypass_guidance():
    from ripper.ai_engine import answer_user_query
    resp = answer_user_query("how to bypass https://gplinks.co/test123")
    assert resp.action_type == "bypass"
    assert "ripper -b" in resp.suggested_command
    assert "https://gplinks.co/test123" in resp.suggested_command


def test_ai_copilot_playback_recommendation():
    from ripper.ai_engine import answer_user_query
    resp = answer_user_query("play loki season 2 episode 1 in 1080p")
    assert resp.action_type == "search"
    assert "loki" in resp.suggested_command
    assert "-q 1080p" in resp.suggested_command
    assert "-w" in resp.suggested_command


def test_autodetect_intent_ai_assistant():
    plan = classify_user_input("what can this ai do with")
    assert plan.intent == InputIntent.AI_ASSISTANT
    assert plan.ai_plan is not None
    assert "K2-Horizon 1B" in plan.ai_plan.answer


def test_ai_self_healing_watchdog():
    from ripper.ai_engine.self_healing import AISelfHealingWatchdog
    wd = AISelfHealingWatchdog()
    wd.activate()
    wd.record_event(
        anomaly_type="ParserWarning",
        source_module="test_module",
        root_cause="simulated warning",
        remediation_applied="re-routed to regex",
    )
    rep = wd.get_health_report()
    assert rep["status"] == "ONLINE & PROTECTING"
    assert rep["intercepted_issues"] == 1
    assert rep["auto_healed_issues"] == 1
    assert rep["health_score_pct"] == 100.0


@pytest.mark.anyio
async def test_auto_heal_decorators():
    from ripper.ai_engine.self_healing import auto_heal

    @auto_heal(fallback_value="SYNC_HEALED")
    def sync_fail():
        raise KeyError("missing_key")

    @auto_heal(fallback_value=["ASYNC_HEALED"])
    async def async_fail():
        raise ConnectionResetError("connection dropped")

    assert sync_fail() == "SYNC_HEALED"
    assert await async_fail() == ["ASYNC_HEALED"]


def test_sitemap_xml_warning_silenced(warnings_recorder=None):
    import warnings
    from ripper.search import _parse_sitemap_locs
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        xml = '<?xml version="1.0"?><urlset><url><loc>https://example.com/item1</loc></url></urlset>'
        res = _parse_sitemap_locs(xml)
        assert res == ["https://example.com/item1"]
        for w in record:
            assert "XMLParsedAsHTMLWarning" not in str(w.message)