"""
Unit Tests for Phase 3: Modular Deep Portal Resolvers
"""

import pytest
import base64
import json
from ripper.portals import (
    safe_get,
    ALL_PORTAL_RESOLVERS,
    resolve_portal_url,
    decrypt_hdhub4u_gadgetsweb_token,
    PixelDrainPortal,
)


def test_safe_get_tree_traversal():
    data = {
        "props": {
            "pageProps": {
                "file": {
                    "downloadUrl": "https://cdn.example.com/movie.mkv",
                    "mirrors": ["https://m1.com", "https://m2.com"],
                }
            }
        }
    }
    # Success cases
    assert safe_get(data, "props", "pageProps", "file", "downloadUrl") == "https://cdn.example.com/movie.mkv"
    assert safe_get(data, "props", "pageProps", "file", "mirrors", 1) == "https://m2.com"

    # Missing key cases (Never crash with KeyError/IndexError)
    assert safe_get(data, "props", "missingKey", default="DEFAULT") == "DEFAULT"
    assert safe_get(data, "props", "pageProps", "file", "mirrors", 99, default=None) is None
    assert safe_get(None, "props", default=None) is None


def test_hdhub4u_rot13_base64_formula():
    # Build synthetic token matching HDHub4u encryption:
    # Target: HubCloud URL -> Base64 -> Put into dict {'o': ...} -> JSON -> Base64 -> Rot13 -> Base64 -> Base64
    target_hubcloud_url = "https://hubcloud.cx/drive/sample12345"
    b64_target = base64.b64encode(target_hubcloud_url.encode()).decode()
    json_data = json.dumps({"o": b64_target})
    s4 = base64.b64encode(json_data.encode()).decode()

    # Invert rot13 to simulate encryption
    rot13_s4 = "".join(
        chr((ord(c) - ord('a' if c.islower() else 'A') + 13) % 26 + ord('a' if c.islower() else 'A'))
        if c.isalpha() else c for c in s4
    )
    s2 = base64.b64encode(rot13_s4.encode()).decode()
    token = base64.b64encode(s2.encode()).decode()

    # Now test our production decryptor
    decrypted = decrypt_hdhub4u_gadgetsweb_token(token)
    assert decrypted == target_hubcloud_url


def test_pixeldrain_portal():
    p = PixelDrainPortal()
    assert p.can_handle("https://pixeldrain.com/u/abc12345") is True

    import anyio
    import httpx
    # Fake call since it computes synchronously without hitting network
    client = httpx.AsyncClient()
    import asyncio
    res = asyncio.run(p.resolve(client, "https://pixeldrain.com/u/abc12345"))
    assert len(res) == 1
    assert res[0].direct_url == "https://pixeldrain.com/api/file/abc12345"


def test_portal_registry_domains():
    expected_matches = {
        "https://vegamovies.ph/download": "VegaMovies / V-Cloud",
        "https://hubcloud.cx/drive/123": "HDHub4u / HubCloud",
        "https://olamovies.art/view": "OlaMovies / OMDrive V3",
        "https://katmoviehd.to/post": "KatmovieHD / KatDrive",
        "https://cinefreak.net/film": "CineFreak / CineCloud",
        "https://pixeldrain.com/u/xyz": "PixelDrain FastDL",
    }

    for url, portal_name in expected_matches.items():
        matched = [p for p in ALL_PORTAL_RESOLVERS if p.can_handle(url)]
        assert len(matched) >= 1
        assert matched[0].name == portal_name
