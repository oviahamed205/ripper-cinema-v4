"""
tests.unit.test_decrypt_lcg
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for 3-layer LCG PRNG cryptographic deobfuscator (MegaCloud / Rabbit).
"""

import pytest
from ripper.resolver.core.decrypt_lcg import (
    atob,
    keygen2,
    seed_shuffle2,
    columnar_cipher2,
    decrypt_src_2,
)


def test_atob_decoding():
    assert atob("aGVsbG8=") == "hello"
    assert atob("aGVsbG8") == "hello"  # unpadded
    assert atob("") == ""
    assert atob("!!!invalid-b64!!!") == ""


def test_keygen2_interleaving():
    k1 = "abc"
    k2 = "12345"
    res = keygen2(k1, k2)
    assert res == "a1b2c345"


def test_seed_shuffle2_deterministic():
    char_array = [chr(32 + i) for i in range(95)]
    s1 = seed_shuffle2(char_array, "test_key_123")
    s2 = seed_shuffle2(char_array, "test_key_123")
    assert s1 == s2
    assert len(s1) == 95
    assert set(s1) == set(char_array)

    # Different key produces different permutation
    s3 = seed_shuffle2(char_array, "other_key_456")
    assert s1 != s3


def test_columnar_cipher2_reconstruction():
    text = "ABCDEFGHIJKLMNOP"
    key = "1234"
    res = columnar_cipher2(text, key)
    assert len(res) == len(text)
    assert columnar_cipher2("", key) == ""


def test_decrypt_src_2_graceful_failures():
    assert decrypt_src_2("", "client", "mega") == ""
    assert decrypt_src_2("short", "client", "mega") == ""
    assert decrypt_src_2("invalid_data_here", "client", "mega") == ""
