"""
Test suite for Media & Episode Grid Scoped Extraction with user's Spider-Man example.
"""

import unittest
import base64
import sys

sys.path.insert(0, r"C:\Users\M Y T H O S\.gemini\antigravity\scratch\unshorten-cli")

from ripper.media import extract_media_items_from_html
from ripper.resolver import extract_url_from_query_params

TEST_SPIDERMAN_HTML = """
<div class="download-links-div">
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> SD 480p [530 MB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvODAzYTllOWZuZXdnbzMy">Download Links</a>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HEVC 720p [900 MB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvYmJjNmRlMDhuZXdnbzMy">Download Links</a>
        <a class="dlbtn dlbtn-watch" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL3gvYmJjNmRlMDhuZXdnbzMy">Watch Online</a>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HD 720p [1.3 GB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvOWRhNzQ3MjVuZXdnbzMy">Download Links</a>
        <a class="dlbtn dlbtn-watch" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL3gvOWRhNzQ3MjVuZXdnbzMy">Watch Online</a>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HEVC 1080p [aaaa]
    </h4>
    <div class="dlbtn-container">
        <span class="uploading">⏳ Uploading Soon...</span>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HD 1080p [3 GB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvOTg0NDdiYTJuZXdnbzMy">Download Links</a>
        <a class="dlbtn dlbtn-watch" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL3gvOTg0NDdiYTJuZXdnbzMy">Watch Online</a>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HQ-Low 1080p [10 GB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvYzE0MDM2YTNuZXdnbzMy">Download Links</a>
        <a class="dlbtn dlbtn-watch" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL3gvYzE0MDM2YTNuZXdnbzMy">Watch Online</a>
    </div>
    <hr>
    <h4 class="movie-title">
        Spider-Man: Brand New Day (2026) <span>[Hindi LiNE & English]</span> HQ 1080p [19 GB]
    </h4>
    <div class="dlbtn-container">
        <a class="dlbtn dlbtn-download" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL2YvMGVmNjk4YjluZXdnbzMy">Download Links</a>
        <a class="dlbtn dlbtn-watch" href="https://cinefreak.net/generate.php?id=aHR0cHM6Ly9uZXc1LmNpbmVjbG91ZC5zaXRlL3gvMGVmNjk4YjluZXdnbzMy">Watch Online</a>
    </div>
</div>
"""

class TestSpidermanScopedExtraction(unittest.TestCase):

    def test_extract_exact_spiderman_qualities(self):
        items = extract_media_items_from_html(TEST_SPIDERMAN_HTML, "https://cinefreak.net")
        
        # Must extract exactly 6 download items and ignore all watch online links & uploading soon
        self.assertEqual(len(items), 6)

        # 1. SD 480p [530 MB]
        self.assertEqual(items[0].codec, "SD")
        self.assertEqual(items[0].quality, "480P")
        self.assertEqual(items[0].size_str, "530 MB")
        self.assertEqual(items[0].unshortened_landing_url, "https://new5.cinecloud.site/f/803a9e9f")

        # 2. HEVC 720p [900 MB]
        self.assertEqual(items[1].codec, "HEVC")
        self.assertEqual(items[1].quality, "720P")
        self.assertEqual(items[1].size_str, "900 MB")
        self.assertEqual(items[1].unshortened_landing_url, "https://new5.cinecloud.site/f/bbc6de08")

        # 3. HD 720p [1.3 GB]
        self.assertEqual(items[2].codec, "HD")
        self.assertEqual(items[2].quality, "720P")
        self.assertEqual(items[2].size_str, "1.3 GB")
        self.assertEqual(items[2].unshortened_landing_url, "https://new5.cinecloud.site/f/9da74725")

        # 4. HD 1080p [3 GB]
        self.assertEqual(items[3].codec, "HD")
        self.assertEqual(items[3].quality, "1080P")
        self.assertEqual(items[3].size_str, "3 GB")
        self.assertEqual(items[3].unshortened_landing_url, "https://new5.cinecloud.site/f/98447ba2")

        # 5. HQ-Low 1080p [10 GB]
        self.assertEqual(items[4].codec, "HQ-LOW")
        self.assertEqual(items[4].quality, "1080P")
        self.assertEqual(items[4].size_str, "10 GB")
        self.assertEqual(items[4].unshortened_landing_url, "https://new5.cinecloud.site/f/c14036a3")

        # 6. HQ 1080p [19 GB]
        self.assertEqual(items[5].codec, "HQ")
        self.assertEqual(items[5].quality, "1080P")
        self.assertEqual(items[5].size_str, "19 GB")
        self.assertEqual(items[5].unshortened_landing_url, "https://new5.cinecloud.site/f/0ef698b9")

    def test_rank_and_badge_servers_prefers_r2(self):
        from ripper.models import ServerMirror
        from ripper.interactive import rank_and_badge_servers

        s_pd = ServerMirror(label="PixelDrain Mirror", intermediate_url="https://pixeldrain.com/u/abc12345")
        s_r2 = ServerMirror(label="Fast Cloud Stream", intermediate_url="https://r2.dev/stream/video.mkv", direct_download_url="https://pub-abc.r2.dev/movie.mkv")
        s_generic = ServerMirror(label="Generic Host", intermediate_url="https://somehost.net/download/123")

        servers = [s_pd, s_generic, s_r2]
        sorted_servers, has_r2 = rank_and_badge_servers(servers)

        self.assertTrue(has_r2)
        self.assertEqual(sorted_servers[0].label, "Fast Cloud Stream")
        self.assertEqual(sorted_servers[1].label, "PixelDrain Mirror")
        self.assertEqual(sorted_servers[2].label, "Generic Host")

    def test_rank_and_badge_servers_fallback(self):
        from ripper.models import ServerMirror
        from ripper.interactive import rank_and_badge_servers

        s_pd = ServerMirror(label="PixelDrain Mirror", intermediate_url="https://pixeldrain.com/u/abc12345")
        s_generic = ServerMirror(label="Generic Host", intermediate_url="https://somehost.net/download/123")

        servers = [s_generic, s_pd]
        sorted_servers, has_r2 = rank_and_badge_servers(servers)

        self.assertFalse(has_r2)
        self.assertEqual(sorted_servers[0].label, "PixelDrain Mirror")
        self.assertEqual(sorted_servers[1].label, "Generic Host")


    def test_extract_vegamovies_all_qualities(self):
        vega_html = """
        <article class="post-content">
            <h1>Deadpool &amp; Wolverine (2024) Hindi Dubbed Org DD5.1 + English</h1>
            <h5>Marvel Studios - Deadpool & Wolverine (2024) {Hindi + English} 480p BluRay [590MB]</h5>
            <p><a href="https://nexdrive.fit/gen1">Download Now</a></p>
            <h5>Marvel Studios - Deadpool & Wolverine (2024) (Hindi + English) 720p 10Bit HEVC [850MB]</h5>
            <p><a href="https://nexdrive.fit/gen2">Download Now</a></p>
            <h5>Marvel Studios - Deadpool & Wolverine (2024) (Hindi DDP 5.1 + English) 1080p BluRay [2.6GB]</h5>
            <p><a href="https://nexdrive.fit/gen3">Download Now</a></p>
            <h5>Marvel Studios - Deadpool & Wolverine (2024) (Hindi DDP 5.1 + English) 2160p 4K UHD Remux HDR10 [49.5GB]</h5>
            <p><a href="https://nexdrive.fit/gen4">Download Now</a></p>
        </article>
        """
        items = extract_media_items_from_html(vega_html, "https://vegamovies.futbol")
        self.assertEqual(len(items), 4)
        qualities = [it.quality for it in items]
        self.assertIn("480P", qualities)
        self.assertIn("720P", qualities)
        self.assertIn("1080P", qualities)
        self.assertIn("2160P", qualities)
        sizes = [it.size_str for it in items]
        self.assertEqual(sizes, ["590MB", "850MB", "2.6GB", "49.5GB"])

    def test_extract_katmoviehd_and_kmmovies_buttons(self):
        html = """
        <div class="entry-content">
            <h1>Avengers Endgame (2019) Dual Audio</h1>
            <p><a href="https://links.kmhd.eu/file/abc1">480p Links [450MB]</a></p>
            <p><a href="https://links.kmhd.eu/file/abc2">720p Links [1.2GB]</a></p>
            <p><a href="https://gd.kmhd.eu/file/abc3">1080p x264 [6GB]</a></p>
            <p><a class="dl-btn" href="https://magiclinks.lol/file/abc4">2160p HDR [18GB]</a></p>
        </div>
        """
        items = extract_media_items_from_html(html, "https://katmoviehd.top")
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0].quality, "480P")
        self.assertEqual(items[0].size_str, "450MB")
        self.assertEqual(items[1].quality, "720P")
        self.assertEqual(items[1].size_str, "1.2GB")
        self.assertEqual(items[2].quality, "1080P")
        self.assertEqual(items[2].size_str, "6GB")
        self.assertEqual(items[3].quality, "2160P")
        self.assertEqual(items[3].size_str, "18GB")


if __name__ == "__main__":
    unittest.main()
