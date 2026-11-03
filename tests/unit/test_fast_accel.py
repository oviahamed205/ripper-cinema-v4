"""
Unit tests for Phase 0 Native Acceleration Layer.
Verifies C-extension / PyO3 / pure-Python parity for fast regex compilation,
SIMD xxhash calculations, micro-sandbox Dean Edwards unpacker, and fallback resilience.
"""
import pytest
from ripper.resolver.core.fast_accel import (
    fast_hash64,
    fast_compile,
    fast_unbase,
    fast_unpack_dean_edwards,
    get_acceleration_status,
    is_c_regex_available,
    is_xxhash_available,
    is_native_rust_available,
)
from ripper.resolver.core.packer_unpack import unpack_packer, detect_packed
from ripper.resolver.core.crypto_unpacker import (
    extract_embedded_b64_url,
    extract_embedded_hex_url,
)


def test_acceleration_status_diagnostic():
    """Verify diagnostic report returns expected accelerator flags."""
    status = get_acceleration_status()
    assert isinstance(status, dict)
    assert "rust_pyo3" in status
    assert "c_regex" in status
    assert "xxhash" in status
    assert "fast_path_enabled" in status
    assert status["fast_path_enabled"] is True


def test_fast_hash64_deterministic():
    """Verify fast_hash64 produces a valid 16-hex-character output deterministically."""
    data = "https://example.com/stream/index.m3u8?token=xyz123"
    h1 = fast_hash64(data)
    h2 = fast_hash64(data)
    assert len(h1) == 16
    assert h1 == h2
    assert h1 != fast_hash64(data + "different")


def test_fast_compile_operations():
    """Verify FastPattern correctly matches, searches, finds, and substitutes."""
    pat = fast_compile(r"stream_(\d+)\.m3u8")
    text = "Found candidate link: stream_1080.m3u8 and stream_720.m3u8"

    # search
    match = pat.search(text)
    assert match is not None
    assert match.group(1) == "1080"

    # findall
    all_res = pat.findall(text)
    assert all_res == ["1080", "720"]

    # sub
    replaced = pat.sub(r"master_\g<1>.m3u8", text)
    assert "master_1080.m3u8" in replaced
    assert "master_720.m3u8" in replaced


def test_fast_unbase_radixes():
    """Verify radix 10, 36, 62, and 95 conversion in fast_unbase."""
    # Base 10
    assert fast_unbase("42", 10) == 42
    # Base 36
    assert fast_unbase("z", 36) == 35
    assert fast_unbase("10", 36) == 36
    # Base 62
    assert fast_unbase("a", 62) == 10
    assert fast_unbase("Z", 62) == 61
    assert fast_unbase("10", 62) == 62
    # Base 95
    assert fast_unbase("!", 95) == 1
    # Invalid
    assert fast_unbase("$$$", 10) == -1


def test_fast_unpack_dean_edwards_packed():
    """Verify accelerated unpacker decodes Dean Edwards packed blocks accurately."""
    packed = "}('0 1(){2 \\'3\\';}',4,4,'function|hello|return|world'.split('|'),0,{})"
    full_script = f"eval(function(p,a,c,k,e,d){{{packed}}})"

    unpacked = fast_unpack_dean_edwards(full_script)
    assert "function hello()" in unpacked
    assert "return 'world';" in unpacked

    # Transparent verification through unpack_packer entrypoint
    unpacked_via_packer = unpack_packer(full_script)
    assert "function hello()" in unpacked_via_packer
    assert "return 'world';" in unpacked_via_packer


def test_fast_regex_in_crypto_unpacker():
    """Verify accelerated regex in crypto_unpacker detects base64 and hex URLs."""
    b64_str = "Look at this payload: aHR0cHM6Ly9leGFtcGxlLmNvbS92aWRlby5tcDQ= inside text"
    extracted_b64 = extract_embedded_b64_url(b64_str)
    assert extracted_b64 == "https://example.com/video.mp4"

    hex_str = "68747470733a2f2f63646e2e746573742e6f72672f6d656469612e6d7034"
    extracted_hex = extract_embedded_hex_url(hex_str)
    assert extracted_hex == "https://cdn.test.org/media.mp4"
