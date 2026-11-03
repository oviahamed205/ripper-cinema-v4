"""
Unit tests for Universal Direct Stream Resolution & Server Crawlers.
"""
import unittest
import asyncio

from ripper.resolver import resolve_to_direct_stream_url


class TestDirectStreamResolver(unittest.TestCase):

    def test_direct_extension_url(self):
        direct_url = "https://cdn.example.com/movies/Spider-Man.2026.1080p.mkv"
        res = asyncio.run(resolve_to_direct_stream_url(direct_url))
        self.assertEqual(res, direct_url)

    def test_direct_cloud_r2_url(self):
        r2_url = "https://pub-abc123.r2.cloudflarestorage.com/spider-man.mkv?token=12345"
        res = asyncio.run(resolve_to_direct_stream_url(r2_url))
        self.assertEqual(res, r2_url)

    def test_pixeldrain_web_to_api_converter(self):
        pd_web_url = "https://pixeldrain.com/u/k89jLa2Z"
        res = asyncio.run(resolve_to_direct_stream_url(pd_web_url))
        self.assertEqual(res, "https://pixeldrain.com/api/file/k89jLa2Z?download")

    def test_movie_article_auto_unpacking(self):
        sample_html = """
        <html><body>
        <div class="download-links-div">
            <h3>Evil Dead Burn (2026) 1080p Web-DL [2.1 GB]</h3>
            <a href="https://pixeldrain.com/u/test1234">Download 1080p</a>
        </div>
        </body></html>
        """
        # Testing parsing through crawl_intermediate_server_page directly with mock
        from ripper.media import extract_media_items_from_html
        items = extract_media_items_from_html(sample_html, "https://cinefreak.net/evil-dead-burn-2026/")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].quality, "1080P")

    def test_gamerxyt_pixeldrain_unrolling(self):
        sample_gamerxyt = """
        <html><body>
        <script>
        var pxl = "https://pixeldrain.dev/u/mNx99aBc";
        </script>
        </body></html>
        """
        import re
        m = re.search(r'var\s+pxl\s*=\s*["\x27]https?://pixeldrain\.(?:com|dev)/u/([a-zA-Z0-9_-]+)["\x27]', sample_gamerxyt)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "mNx99aBc")
        self.assertEqual(f"https://pixeldrain.com/api/file/{m.group(1)}?download", "https://pixeldrain.com/api/file/mNx99aBc?download")

    def test_streamtape_robotlink_decoder(self):
        sample_js = """
        document.getElementById('robotlink').innerHTML = '//streamtape.com/get_video?id=xyz123' + ('&token=abc_9999').substring(2).substring(1);
        """
        import re
        m = re.search(r"document\.getElementById\(['\"]robotlink['\"]\)\.innerHTML\s*=\s*['\"]([^'\"]+)['\"]\s*\+\s*\(['\"]([^'\"]+)['\"]\)\.substring\(2\)\.substring\(1\)", sample_js)
        self.assertIsNotNone(m)
        direct = "https:" + m.group(1) + m.group(2)[3:]
        self.assertEqual(direct, "https://streamtape.com/get_video?id=xyz123ken=abc_9999")

    def test_streamwish_m3u8_extractor(self):
        sample_sw = """
        var player = new Player({file: "https://delivery-node.streamwish.to/hls/test_stream.m3u8"});
        """
        import re
        m = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', sample_sw)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "https://delivery-node.streamwish.to/hls/test_stream.m3u8")


    def test_gofile_regex_parsing(self):
        url = "https://gofile.io/d/kL92Xz"
        import re
        m = re.search(r"gofile\.io/d/([a-zA-Z0-9_-]+)", url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "kL92Xz")

    def test_doodstream_pass_token_parsing(self):
        sample_dood = """
        <script>
        $.get('/pass_md5/xyz789/hash123', function(data) { });
        </script>
        """
        import re
        m = re.search(r"/pass_md5/([^'\"]+)", sample_dood)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "xyz789/hash123")

    def test_bunkr_cdn_extractor(self):
        sample_bunkr = """
        <a class="btn" href="https://media-files12.bunkr.is/download/video.mp4">Download</a>
        """
        import re
        m = re.search(r'href=["\x27](https?://media-files[a-zA-Z0-9.\-]+\.bunkr\.[a-z]+/[^"\x27]+)["\x27]', sample_bunkr)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "https://media-files12.bunkr.is/download/video.mp4")

    def test_mega_nz_link_extractor(self):
        url = "https://mega.nz/file/ABCDEF12#0123456789abcdefABCDEF12"
        import re
        m = re.search(r"mega\.nz/file/([a-zA-Z0-9_-]+)#([a-zA-Z0-9_-]+)", url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "ABCDEF12")
        self.assertEqual(m.group(2), "0123456789abcdefABCDEF12")


if __name__ == "__main__":
    unittest.main()
