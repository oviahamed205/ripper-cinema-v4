"""
Unit tests for the new 'Last Ship' Indestructible Hybrid Resolver modules:
- Dean Edwards P.A.C.K.E.R Unpacker (radix 10, 36, 62, 95)
- DNS-over-HTTPS (DoH) engine with fallback and caching
- Video Hosts Resolver Plugin (DoodStream, MixDrop, StreamWish, Voe.sx, Filemoon, Kwik)
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ripper.resolver.core.packer_unpack import unpack_packer, detect_packed, Unbaser
from ripper.resolver.core.doh_resolver import resolve_doh, clear_doh_cache, _DOH_CACHE
from ripper.resolver.handlers.video_hosts import VideoHostsHandler
from ripper.resolver.base import ResolutionContext


class TestPackerUnpacker(unittest.TestCase):
    def test_packer_unbaser(self):
        u62 = Unbaser(62)
        self.assertEqual(u62("0"), 0)
        self.assertEqual(u62("1"), 1)
        self.assertEqual(u62("a"), 10)
        self.assertEqual(u62("z"), 35)
        self.assertEqual(u62("A"), 36)
        self.assertEqual(u62("Z"), 61)
        self.assertEqual(u62("10"), 62)

    def test_packer_unpacker_basic(self):
        packed = "}('0 1(){2 \'3\';}',4,4,'function|hello|return|world'.split('|'),0,{})"
        full_script = f"eval(function(p,a,c,k,e,d){{{packed}}})"
        self.assertTrue(detect_packed(full_script))
        unpacked = unpack_packer(full_script)
        self.assertIn("function hello()", unpacked)
        self.assertIn("return 'world';", unpacked)

    def test_packer_unpacker_radix_62(self):
        packed = "}('0.1(\'2 3\');',4,4,'console|log|hello|universe'.split('|'))"
        full_script = f"eval(function(p,a,c,k,e,d){{{packed}}})"
        unpacked = unpack_packer(full_script)
        self.assertIn("console.log('hello universe');", unpacked)


class TestDoHResolver(unittest.IsolatedAsyncioTestCase):
    async def test_doh_resolution_cloudflare(self):
        clear_doh_cache()
        ip = await resolve_doh("cloudflare.com", timeout=5.0)
        self.assertIsNotNone(ip)
        self.assertEqual(len(ip.split(".")), 4)
        self.assertIn("cloudflare.com", _DOH_CACHE)
        cached_ip = await resolve_doh("cloudflare.com")
        self.assertEqual(cached_ip, ip)


class TestVideoHostsHandler(unittest.IsolatedAsyncioTestCase):
    async def test_video_hosts_can_handle(self):
        h = VideoHostsHandler()
        self.assertTrue(h.can_handle("https://doodstream.com/e/abc123xyz"))
        self.assertTrue(h.can_handle("https://d0000d.com/e/abc123xyz"))
        self.assertTrue(h.can_handle("https://mixdrop.co/e/123456"))
        self.assertTrue(h.can_handle("https://streamwish.to/e/987654"))
        self.assertTrue(h.can_handle("https://voe.sx/e/xyz789"))
        self.assertTrue(h.can_handle("https://filemoon.sx/e/fm123"))
        self.assertTrue(h.can_handle("https://kwik.cx/e/kw123"))
        self.assertFalse(h.can_handle("https://google.com"))

    async def test_video_hosts_mixdrop(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        packed_page = """
        <html><head></head><body>
        <script>
        eval(function(p,a,c,k,e,d){return p}('MDCore.wurl="//s-delivery.mixdrop.co/v/video.mp4";',1,1,''.split('|')))
        </script>
        </body></html>
        """
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.text = packed_page
            mock_req.return_value = mock_res

            res = await h.resolve("https://mixdrop.co/e/abc123xyz", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://s-delivery.mixdrop.co/v/video.mp4")
            self.assertEqual(hops[-1].redirect_type, "mixdrop_direct_stream")

    async def test_video_hosts_streamwish(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        sw_page = """
        <html><body>
        <script>
        var player = jwplayer("vplayer");
        sources: [{file: "https://streamwish.to/hls/master.m3u8"}];
        </script>
        </body></html>
        """
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.text = sw_page
            mock_req.return_value = mock_res

            res = await h.resolve("https://streamwish.to/e/sw123", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://streamwish.to/hls/master.m3u8")
            self.assertEqual(hops[-1].redirect_type, "streamwish_hls_stream")

    async def test_video_hosts_voe(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        voe_page = """
        <html><body>
        <script>
        'hls': 'https://voecdn.net/engine/master.m3u8'
        </script>
        </body></html>
        """
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.text = voe_page
            mock_req.return_value = mock_res

            res = await h.resolve("https://voe.sx/e/voe123", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://voecdn.net/engine/master.m3u8")
            self.assertEqual(hops[-1].redirect_type, "voe_hls_stream")

    async def test_video_hosts_doodstream(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        embed_html = """
        <html><body>
        <script>
        $.get('/pass_md5/randomtoken123', function(data) {});
        var a = '?token=abctoken456&expiry=123456';
        </script>
        </body></html>
        """
        pass_res_text = "https://doodstream.delivery/stream/"
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_embed = MagicMock()
            mock_embed.status_code = 200
            mock_embed.text = embed_html

            mock_pass = MagicMock()
            mock_pass.status_code = 200
            mock_pass.text = pass_res_text

            mock_req.side_effect = [mock_embed, mock_pass]

            res = await h.resolve("https://doodstream.com/e/dood123", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertTrue(direct_url.startswith("https://doodstream.delivery/stream/"))
            self.assertIn("token=abctoken456", direct_url)
            self.assertEqual(hops[-1].redirect_type, "doodstream_direct_stream")

    async def test_video_hosts_vidhide(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        vidhide_html = """
        <html><body>
        <script>
        links = {
            hls4: 'https://vidhidecdn.net/hls4/master.m3u8',
            hls3: 'https://vidhidecdn.net/hls3/master.m3u8'
        };
        </script>
        </body></html>
        """
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.text = vidhide_html
            mock_req.return_value = mock_res

            res = await h.resolve("https://vidhide.com/v/vh123", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://vidhidecdn.net/hls4/master.m3u8")
            self.assertEqual(hops[-1].redirect_type, "vidhide_hls_stream")

    async def test_video_hosts_luluvdo(self):
        h = VideoHostsHandler()
        ctx = ResolutionContext()
        mock_client = MagicMock()
        luluvdo_html = """
        <html><body>
        <script>
        var player = 'https://lulustream.net/stream/master.m3u8';
        </script>
        </body></html>
        """
        with patch("ripper.resolver.handlers.video_hosts.request_capped") as mock_req:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.text = luluvdo_html
            mock_req.return_value = mock_res

            res = await h.resolve("https://luluvdo.com/e/lulu123", mock_client, ctx)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://lulustream.net/stream/master.m3u8")
            self.assertEqual(hops[-1].redirect_type, "luluvdo_hls_stream")

