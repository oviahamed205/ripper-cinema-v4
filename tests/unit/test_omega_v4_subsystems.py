"""
Comprehensive Unit & Integration Tests for Ripper v4.0 Omega Subsystems:
1. Bayesian Multi-Armed Bandit (Thompson Sampling) Mirror Router
2. Speculative Parallel Hop Predictor (First-Order Markov Chain)
3. 7-Pass Symbolic & AST JavaScript Deobfuscator
4. Model Context Protocol (MCP) JSON-RPC 2.0 Server
5. CLI Omega Flags (--bandit-stats, --predict-hops, --deobfuscate, --omega-bench)
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from click.testing import CliRunner

from ripper.cli import main
from ripper.mcp_server import RipperMCPServer, run_omega_benchmark
from ripper.resolver.core import (
    ThompsonBanditRouter,
    SpeculativeHopPredictor,
    deobfuscate_javascript_ast,
)


def test_thompson_bandit_router_priors_and_learning(tmp_path: Path):
    state_file = tmp_path / "bandit_test.json"
    router = ThompsonBanditRouter(state_path=state_file)

    candidates = [
        "https://voe.sx/e/slow_stream",
        "https://pixeldrain.com/api/file/fast1",
        "https://pub-123.r2.cloudflarestorage.com/movie.mkv",
    ]
    ranked = router.rank_urls(candidates, deterministic=True)
    assert len(ranked) == 3
    # R2 has the strongest informed prior and lowest latency
    assert ranked[0]["arm_id"] == "r2.cloudflarestorage.com"
    assert ranked[1]["arm_id"] == "pixeldrain.com"

    # Record failures on R2 and successes on PixelDrain to verify posterior online learning
    for _ in range(25):
        router.record_outcome(candidates[2], success=False, latency_ms=2500.0)
        router.record_outcome(candidates[1], success=True, latency_ms=45.0)

    updated = router.rank_urls(candidates, deterministic=True)
    assert updated[0]["arm_id"] == "pixeldrain.com"
    assert state_file.exists()

    # Reload from disk and verify persistence
    router2 = ThompsonBanditRouter(state_path=state_file)
    reloaded = router2.rank_urls(candidates, deterministic=True)
    assert reloaded[0]["arm_id"] == "pixeldrain.com"


@pytest.mark.asyncio
async def test_speculative_hop_predictor_markov_chain(tmp_path: Path):
    graph_file = tmp_path / "hop_graph.json"
    predictor = SpeculativeHopPredictor(graph_path=graph_file)

    # Record custom multi-hop observation
    for _ in range(10):
        predictor.record_chain([
            "https://short.omega.test/abc",
            "https://gate.omega.test/verify",
            "https://r2.cloudflarestorage.com/final.mkv",
        ])

    next_hops = predictor.predict_next_domains("https://short.omega.test/xyz")
    assert len(next_hops) >= 1
    assert next_hops[0][0] == "gate.omega.test"
    assert next_hops[0][1] == 1.0

    chain = predictor.predict_chain("https://short.omega.test/xyz", max_steps=3)
    assert len(chain) == 2
    assert chain[0].predicted_domain == "gate.omega.test"
    assert chain[1].predicted_domain == "r2.cloudflarestorage.com"


def test_ast_javascript_deobfuscator_7_pass():
    obfuscated = """
    if (false) {
        window.location.href = "https://honeypot-trap.invalid/malware.exe";
    }
    var _0xabc1 = ["https://", "pub-777.r2.cloudflarestorage.com", "/streams/blade_runner_2049_4k.m3u8"];
    var target = _0xabc1[0] + _0xabc1[1] + _0xabc1[2];
    var backup = atob("aHR0cHM6Ly9waXhlbGRyYWluLmNvbS9hcGkvZmlsZS9vbWVnYTQy");
    var third = String.fromCharCode(104, 116, 116, 112, 115, 58, 47, 47) + "\\x67\\x6f\\x66\\x69\\x6c\\x65.io/d/999";
    """
    res = deobfuscate_javascript_ast(obfuscated)
    assert "honeypot-trap.invalid" not in res.deobfuscated_source
    assert "https://pub-777.r2.cloudflarestorage.com/streams/blade_runner_2049_4k.m3u8" in res.extracted_urls
    assert "https://pixeldrain.com/api/file/omega42" in res.extracted_urls
    assert "https://gofile.io/d/999" in res.extracted_urls
    assert len(res.extracted_streams) >= 2


@pytest.mark.asyncio
async def test_mcp_server_jsonrpc_protocol():
    server = RipperMCPServer()

    init_resp = await server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp["result"]["serverInfo"]["name"] == "ripper-omega-mcp"

    list_resp = await server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = [t["name"] for t in list_resp["result"]["tools"]]
    assert "ripper_deobfuscate_js" in tool_names
    assert "ripper_bandit_rank_mirrors" in tool_names
    assert "ripper_predict_hops" in tool_names

    call_resp = await server.handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "ripper_deobfuscate_js",
            "arguments": {
                "javascript": 'var u = "ht" + "tps://cdn.example.com/video.mp4";',
            },
        },
    })
    structured = call_resp["result"]["structuredContent"]
    assert "https://cdn.example.com/video.mp4" in structured["extracted_urls"]


def test_cli_omega_flags():
    runner = CliRunner()

    r1 = runner.invoke(main, ["--bandit-stats", "--json"])
    assert r1.exit_code == 0
    d1 = json.loads(r1.output)
    assert d1["total_arms_tracked"] >= 10

    r2 = runner.invoke(main, ["--deobfuscate", 'var x = "ht" + "tps://r2.dev/stream.m3u8";', "--json"])
    assert r2.exit_code == 0
    d2 = json.loads(r2.output)
    assert "https://r2.dev/stream.m3u8" in d2["extracted_urls"]

    r3 = runner.invoke(main, ["--omega-bench", "--json"])
    assert r3.exit_code == 0
    d3 = json.loads(r3.output)
    assert d3["version"] == "4.0.0-OMEGA"
    assert "ast_js_deobfuscator" in d3["benchmarks"]
