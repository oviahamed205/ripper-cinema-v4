import os
import json
import pytest
import tempfile
from ripper.healer_engine import (
    RulesCache,
    HeuristicResolution,
    DiagnosticBrain,
    NeuralDiagnosis,
    AstPatcher,
    PatchResult,
    EnvironmentDoctor,
    HealthCheckReport,
    HealerWatchdog,
    get_global_watchdog,
)

def test_rules_cache_xml_warning():
    cache = RulesCache()
    res = cache.match("D:\\ripper\\search.py:700: XMLParsedAsHTMLWarning: It looks like you're using an HTML parser")
    assert res is not None
    assert res.matched is True
    assert res.rule_name == "XML_AS_HTML_WARNING"
    assert "XML" in res.action

def test_rules_cache_cloudflare():
    cache = RulesCache()
    res = cache.match("Client error: 403 Forbidden - Attention Required! | Cloudflare cf-chl-bypass")
    assert res is not None
    assert res.rule_name == "CLOUDFLARE_403_429"
    assert "ROTATE_HEADERS" in res.action

def test_rules_cache_unicode_decode():
    cache = RulesCache()
    res = cache.match("UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte")
    assert res is not None
    assert res.rule_name == "UNICODE_DECODE_ERROR"
    assert "REPLACE" in res.action

def test_rules_cache_json_fences():
    cache = RulesCache()
    res = cache.match("json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)")
    assert res is not None
    assert res.rule_name == "JSON_DECODE_FENCE_ERROR"
    assert "MARKDOWN" in res.action

def test_rules_cache_network_timeout():
    cache = RulesCache()
    res = cache.match("httpx.ConnectTimeout: NameResolutionError: Temporary failure in name resolution")
    assert res is not None
    assert res.rule_name == "NETWORK_CONNECT_TIMEOUT"
    assert "DNS" in res.action

def test_rules_cache_file_lock():
    cache = RulesCache()
    res = cache.match("[WinError 32] The process cannot access the file because it is being used by another process")
    assert res is not None
    assert res.rule_name == "FILE_LOCK_PERMISSION"
    assert "RENAME_AND_COPY" in res.action

def test_rules_cache_missing_parser():
    cache = RulesCache()
    res = cache.match("bs4.FeatureNotFound: Couldn't find a tree builder with the features you requested: lxml.")
    assert res is not None
    assert res.rule_name == "MISSING_BEAUTIFULSOUP_PARSER"
    assert "FALLBACK_HTML_PARSER" in res.action

def test_rules_cache_ssl_error():
    cache = RulesCache()
    res = cache.match("ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    assert res is not None
    assert res.rule_name == "SSL_CERTIFICATE_VERIFY_FAILED"
    assert "LOAD_CERTIFI_CA_BUNDLE" in res.action

def test_ast_patcher_validation_and_rollback():
    patcher = AstPatcher()
    
    # Valid Python
    assert patcher.validate_code("def add(a, b):\n    return a + b\n") is True
    # Invalid syntax
    assert patcher.validate_code("def add(a, b\n    return a + b\n") is False

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "sample.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("x = 10\ny = 20\n")

        # Safely patch with valid code
        res = patcher.patch_file_safely(test_file, "x = 10\ny = 30\n")
        assert res.success is True
        assert res.backup_path is not None
        assert os.path.exists(res.backup_path)

        with open(test_file, "r", encoding="utf-8") as f:
            assert f.read() == "x = 10\ny = 30\n"

        # Rollback
        rolled_back = patcher.rollback(test_file)
        assert rolled_back is True
        with open(test_file, "r", encoding="utf-8") as f:
            assert f.read() == "x = 10\ny = 20\n"

        # Attempt patching with invalid syntax - should be rejected
        bad_res = patcher.patch_file_safely(test_file, "def broken_syntax(:\n")
        assert bad_res.success is False
        assert "Syntax validation failed" in bad_res.error_message

def test_diagnostic_brain_fallback():
    brain = DiagnosticBrain()
    diag = brain.diagnose(
        traceback_str="Traceback (most recent call last):\n  File 'test.py', line 10\nZeroDivisionError: division by zero",
        stderr_context="Warning: calculation failed"
    )
    assert isinstance(diag, NeuralDiagnosis)
    assert diag.error_type is not None
    assert diag.confidence > 0.0
    assert diag.remediation_recipe is not None

def test_environment_doctor():
    doctor = EnvironmentDoctor()
    report = doctor.run_health_checks()
    assert isinstance(report, HealthCheckReport)
    assert report.python_version is not None
    assert "default_dns_host" in report.diagnostics

def test_watchdog_lifecycle():
    watchdog = HealerWatchdog()
    watchdog.install()
    assert watchdog._installed is True
    
    # Trigger heuristic error
    res = watchdog.handle_error("XMLParsedAsHTMLWarning: Using HTML parser for XML")
    assert res.matched is True
    assert watchdog.remediation_counter >= 1

    # Trigger unmapped error -> triggers Neural Brain fallback
    res2 = watchdog.handle_error("CustomDomainSpecificException: Unexpected state")
    assert res2.matched is True
    assert res2.rule_name == "NEURAL_SLM_DIAGNOSIS"

    watchdog.uninstall()
    assert watchdog._installed is False

def test_schema_validity():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    schema_path = os.path.join(base_dir, "ripper", "healer_engine", "schemas", "patch_plan.json")
    assert os.path.exists(schema_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema["title"] == "PatchPlan"
    assert "plan_id" in schema["required"]

    gbnf_path = os.path.join(base_dir, "ripper", "healer_engine", "schemas", "diagnosis.gbnf")
    assert os.path.exists(gbnf_path)
    with open(gbnf_path, "r", encoding="utf-8") as f:
        gbnf_content = f.read()
    assert "root ::=" in gbnf_content
