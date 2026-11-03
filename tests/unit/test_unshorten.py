"""
Automated unit tests & simulations for unshorten-cli (Enterprise Edition).
"""

import sys
import os
import unittest
import base64

sys.path.insert(0, r"C:\Users\M Y T H O S\.gemini\antigravity\scratch\unshorten-cli")

from ripper.resolver import (
    extract_url_from_query_params,
    extract_meta_refresh_url,
    extract_js_redirect_url,
    extract_server_options_from_html,
    extract_filename_from_url_or_headers,
    unshorten_url_sync,
)
from ripper.safety import analyze_destination_safety, detect_mime_category
from ripper.batch import extract_urls_from_raw_text


class TestUnshortenCore(unittest.TestCase):

    def test_query_param_unwrapping_direct(self):
        url = "https://ad-network.com/redirect?url=https://github.com/torvalds/linux"
        extracted = extract_url_from_query_params(url)
        self.assertEqual(extracted, "https://github.com/torvalds/linux")

    def test_query_param_unwrapping_base64(self):
        target = "https://example.com/download.zip"
        b64 = base64.b64encode(target.encode("utf-8")).decode("utf-8")
        url = f"https://tracker.xyz/out?dest={b64}"
        extracted = extract_url_from_query_params(url)
        self.assertEqual(extracted, target)

    def test_meta_refresh_extraction(self):
        html = '<html><head><meta http-equiv="refresh" content="2;url=https://destination.org/final"></head><body></body></html>'
        extracted = extract_meta_refresh_url(html, "https://initial.org")
        self.assertEqual(extracted, "https://destination.org/final")

    def test_meta_refresh_relative_url(self):
        html = '<meta http-equiv="refresh" content="0;url=/nested/page.html">'
        extracted = extract_meta_refresh_url(html, "https://example.com/start")
        self.assertEqual(extracted, "https://example.com/nested/page.html")

    def test_js_redirect_extraction_location_href(self):
        html = '<script>window.location.href = "https://target-site.com/welcome";</script>'
        extracted = extract_js_redirect_url(html, "https://source.com")
        self.assertEqual(extracted, "https://target-site.com/welcome")

    def test_js_redirect_extraction_location_replace(self):
        html = '<script>location.replace("https://destination.com/app");</script>'
        extracted = extract_js_redirect_url(html, "https://source.com")
        self.assertEqual(extracted, "https://destination.com/app")

    def test_server_options_extraction(self):
        html = '''
        <div class="servers">
            <a href="/d/af315503" onclick="OPEN_NEW_LINK(event)" class="btn btn-sm server-btn btn-cloud">Cloud [Resumable]</a>
            <a href="/d/fast99" class="btn btn-sm server-btn btn-fast">Fast Server [1080p]</a>
        </div>
        '''
        servers = extract_server_options_from_html(html, "https://new5.cinecloud.site/f/af315503")
        self.assertEqual(len(servers), 2)
        self.assertEqual(servers[0][0], "Cloud [Resumable]")
        self.assertEqual(servers[0][1], "https://new5.cinecloud.site/d/af315503")
        self.assertEqual(servers[1][0], "Fast Server [1080p]")
        self.assertEqual(servers[1][1], "https://new5.cinecloud.site/d/fast99")

    def test_filename_extraction_from_presigned_r2_url(self):
        url = "https://93f3f089fdb0f4945c4bfd426158f9f4.r2.cloudflarestorage.com/neodrive/CINEFREAK.TOP%20-%20Lanterns%20%5BS01E01%5D%20WEB-DL%20%5BHindi-English%5D%201080p%20ESub.mkv?response-content-disposition=attachment%3B%20filename%3D%22CINEFREAK.TOP%20-%20Lanterns%20%5BS01E01%5D%20WEB-DL%20%5BHindi-English%5D%201080p%20ESub.mkv%22&X-Amz-Signature=1234"
        fn = extract_filename_from_url_or_headers(url)
        self.assertEqual(fn, "CINEFREAK.TOP - Lanterns [S01E01] WEB-DL [Hindi-English] 1080p ESub.mkv")

    def test_mime_category_cloud_storage(self):
        url = "https://93f3f089fdb0.r2.cloudflarestorage.com/neodrive/file.mkv?token=123"
        self.assertEqual(detect_mime_category(url, "video/x-matroska"), "CLOUD_STORAGE")

    def test_mime_category_detection(self):
        self.assertEqual(detect_mime_category("https://example.com/setup.exe", "application/octet-stream"), "EXECUTABLE")
        self.assertEqual(detect_mime_category("https://example.com/game.rar", "application/x-rar"), "ARCHIVE")
        self.assertEqual(detect_mime_category("https://example.com/doc.pdf", "application/pdf"), "DOCUMENT")
        self.assertEqual(detect_mime_category("https://example.com/song.mp3", "audio/mpeg"), "MEDIA")
        self.assertEqual(detect_mime_category("https://example.com/page", "text/html"), "WEBPAGE")

    def test_safety_scoring_secure_webpage(self):
        report = analyze_destination_safety("https://github.com/python/cpython", content_type="text/html")
        self.assertTrue(report.is_https)
        self.assertEqual(report.risk_level, "SAFE")
        self.assertEqual(report.risk_score, 0)

    def test_raw_text_url_extractor(self):
        raw = """
        Check this link: https://tinyurl.com/abc1234
        Also this one: <a href="https://bit.ly/secret_link">Click</a>
        And plain text: http://example.com/test.zip.
        """
        urls = extract_urls_from_raw_text(raw)
        self.assertEqual(len(urls), 3)
        self.assertIn("https://tinyurl.com/abc1234", urls)
        self.assertIn("https://bit.ly/secret_link", urls)
        self.assertIn("http://example.com/test.zip", urls)

    def test_live_resolution_httpbin(self):
        url = "https://httpbin.org/redirect/2"
        res = unshorten_url_sync(url, max_hops=5)
        self.assertTrue(res.is_success)
        self.assertGreaterEqual(res.total_hops, 2)
        self.assertIn("httpbin.org", res.final_url)

    def test_bot_challenge_detection(self):
        from ripper.resolver import is_bot_challenge
        headers = {"server": "cloudflare", "cf-mitigated": "challenge"}
        html = "<html><head><title>Just a moment...</title></head></html>"
        is_chal, desc = is_bot_challenge(403, headers, html)
        self.assertTrue(is_chal)
        self.assertIn("Cloudflare", desc)

    def test_embedded_b64_url_extraction(self):
        from ripper.resolver import extract_embedded_b64_url
        html = '<input name="token" value="abc123aHR0cHM6Ly9kcml2ZS5vbGFtb3ZpZXMuZG93bmxvYWQvZmlsZS8wMTIzNA==">'
        url = extract_embedded_b64_url(html)
        self.assertEqual(url, "https://drive.olamovies.download/file/01234")


if __name__ == "__main__":
    unittest.main()
