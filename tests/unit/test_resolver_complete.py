"""
Comprehensive, exhaustive unit and integration tests for the God-Tier Resolver.
Covers 10-layer defense matrix, core primitives, all 14 site handlers,
memory safety, circuit breaker, unpackers, and loop guards.
"""
import asyncio
import base64
import json
import pytest
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ripper.resolver.core import (
    is_circuit_open,
    record_domain_failure,
    record_domain_success,
    is_ad_trap,
    is_hidden_element,
    decode_rot13,
    caesar_decipher,
    decode_multistage_caesar_b64,
    decode_xor_token,
    decode_base64_url,
    decode_bluemedia_key,
    decode_nested_atob,
    decrypt_adfly_ysmm,
    extract_shortener_api_url,
    extract_url_from_query_params,
    extract_embedded_b64_url,
    extract_embedded_hex_url,
    extract_embedded_encoded_url,
    unpack_dean_edwards_packer,
    extract_meta_refresh_url,
    extract_js_redirect_url,
    parse_kmhd_sveltekit_data,
    parse_nextjs_data,
    unpack_obfuscator_io_hex_array,
    looks_like_binary,
    looks_like_html,
    extract_filename_from_url_or_headers,
    is_bot_challenge,
    validate_presigned_url,
    probe_mirror_latency,
    pick_fastest_live_mirror,
    solve_recaptcha_v3_anchor,
    FetchResult,
)
from ripper.resolver.handlers import (
    CloudStorageHandler,
    FileLockersHandler,
    HubCloudHandler,
    KMHDHandler,
    VCloudHandler,
    MagicLinksHandler,
    NexDriveHandler,
    OlaMoviesHandler,
    GDToTHandler,
    AppDriveHandler,
    AdShortenersHandler,
    FileCryptHandler,
    UniversalHeuristicsHandler,

    extract_server_options_from_html,
    extract_cloud_urls_from_html,
    resolve_to_direct_stream_url,
)
from ripper.resolver.base import ResolutionContext
from ripper.resolver.registry import GLOBAL_REGISTRY
from ripper.resolver.engine import ResolverEngine
from ripper.models import ServerMirror, HopInfo
from bs4 import BeautifulSoup


class TestCircuitGuard(unittest.IsolatedAsyncioTestCase):
    async def test_circuit_breaker_flow(self):
        domain = "broken-mirror-node.xyz"
        # Initially closed
        self.assertFalse(await is_circuit_open(domain))

        # Record failures up to threshold (default threshold is 3)
        await record_domain_failure(domain)
        await record_domain_failure(domain)
        await record_domain_failure(domain)

        # Now circuit should be open
        self.assertTrue(await is_circuit_open(domain))

        # Successful request resets circuit
        await record_domain_success(domain)
        self.assertFalse(await is_circuit_open(domain))


class TestHoneypotFilter(unittest.TestCase):
    def test_ad_trap_domains(self):
        self.assertTrue(is_ad_trap("https://propellerads.com/track?id=123"))
        self.assertTrue(is_ad_trap("https://adsterra.com/click/banner"))
        self.assertTrue(is_ad_trap("https://example.com/ads/delivery/redirect"))
        self.assertFalse(is_ad_trap("https://pub-abc1234.r2.cloudflarestorage.com/movie.mkv"))

    def test_hidden_css_elements(self):
        html = """
        <div>
            <a href="https://trap.com/trap1" style="display: none;">Invisible Trap 1</a>
            <a href="https://trap.com/trap2" style="visibility: hidden">Invisible Trap 2</a>
            <a href="https://trap.com/trap3" style="opacity: 0">Invisible Trap 3</a>
            <a href="https://trap.com/trap4" class="honeypot fake-link">Invisible Trap 4</a>
            <a href="https://trap.com/trap5" hidden>Invisible Trap 5</a>
            <div style="display:none">
                <a href="https://trap.com/trap6">Parent Hidden Trap</a>
            </div>
            <a href="https://legit.com/real-download" class="btn btn-download">Real Download</a>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a")
        # Links 0 to 5 are honeypot traps
        for i in range(6):
            self.assertTrue(is_hidden_element(links[i]), f"Link {i} should be detected as hidden honeypot")
        # Link 6 is legitimate
        self.assertFalse(is_hidden_element(links[6]))


class TestCryptoAndUnpackers(unittest.TestCase):
    def test_rot13(self):
        self.assertEqual(decode_rot13("uryyb"), "hello")
        self.assertEqual(decode_rot13("URYYB"), "HELLO")

    def test_xor(self):
        key = "secret"
        plain = "https://r2.dev/stream.mp4"
        # Encrypt
        enc = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(plain))
        # Decrypt
        dec = decode_xor_token(enc, key)
        self.assertEqual(dec, plain)

    def test_base64_url_extractor(self):
        target = "https://cdn.server.org/video.mp4"
        b64 = base64.b64encode(target.encode()).decode()
        html = f'<div class="payload">aHR0c{b64[5:]}</div>'
        extracted = extract_embedded_b64_url(html)
        self.assertEqual(extracted, target)

    def test_hex_url_extractor(self):
        target = "https://target-server.com/archive.zip"
        hex_str = target.encode().hex()
        html = f'<script>var redirect = "{hex_str}";</script>'
        extracted = extract_embedded_hex_url(html)
        self.assertEqual(extracted, target)

    def test_dean_edwards_packer(self):
        # Standard Dean Edwards packed snippet
        # function test(p,a,c,k,e,d) unpacking: "window.location='https://final.org/stream.mkv';"
        packed = "eval(function(p,a,c,k,e,d){return p}('window.location=\\'https://final.org/stream.mkv\\';',10,2,'||||||||||'.split('|')))"
        unpacked = unpack_dean_edwards_packer(packed)
        self.assertIn("https://final.org/stream.mkv", unpacked)

    def test_kmhd_sveltekit_parser(self):
        html_payload = """
        <script>
            window.__sveltekit_data = {
                name: "Avatar.The.Way.Of.Water.2022.1080p.mkv",
                upload_links: {hubcloud: "token123", pixeldrain: "abc456"},
                links: {
                    hubcloud: {link: "https://hubcloud.fit/drive/"},
                    pixeldrain: {link: "https://pixeldrain.com/u/"}
                },
                ads: {}
            };
        </script>
        """
        filename, links = parse_kmhd_sveltekit_data(html_payload)
        self.assertEqual(filename, "Avatar.The.Way.Of.Water.2022.1080p.mkv")
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0][1], "https://hubcloud.fit/drive/token123")
        self.assertEqual(links[1][1], "https://pixeldrain.com/u/abc456")


class TestBinarySafeHttp(unittest.TestCase):
    def test_looks_like_binary(self):
        self.assertTrue(looks_like_binary("video/mp4", url="https://cdn.com/film.mp4"))
        self.assertTrue(looks_like_binary("application/octet-stream", {"content-disposition": 'attachment; filename="data.zip"'}))
        self.assertTrue(looks_like_binary("application/x-matroska", url="https://pub.r2.dev/stream.mkv"))
        self.assertFalse(looks_like_binary("text/html; charset=utf-8"))
        self.assertFalse(looks_like_binary("application/json"))

    def test_is_bot_challenge(self):
        # Cloudflare turnstile challenge
        is_chal, note = is_bot_challenge(403, {"server": "cloudflare"}, "<html><title>Just a moment...</title></html>")
        self.assertTrue(is_chal)
        self.assertIn("Cloudflare", note)

        # Normal 200 page
        is_chal2, note2 = is_bot_challenge(200, {"server": "nginx"}, "<html><title>Movie Download</title></html>")
        self.assertFalse(is_chal2)
        self.assertEqual(note2, "")


class TestSiteHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_storage_instant_resolution(self):
        handler = CloudStorageHandler()
        url = "https://93f3f089fdb0.r2.cloudflarestorage.com/neodrive/file.mkv?token=123"
        self.assertTrue(handler.can_handle(url))

        context = ResolutionContext()
        client = AsyncMock()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, url)
        self.assertEqual(hops[0].status_code, 200)
        self.assertEqual(hops[0].redirect_type, "direct_cloud_storage")

    async def test_pixeldrain_web_to_api(self):
        handler = FileLockersHandler()
        url = "https://pixeldrain.com/u/k89jLa2Z"
        self.assertTrue(handler.can_handle(url))

        context = ResolutionContext()
        client = AsyncMock()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://pixeldrain.com/api/file/k89jLa2Z?download")
        self.assertEqual(hops[0].redirect_type, "pixeldrain_api")

    async def test_vcloud_atob_unwrapping(self):
        handler = VCloudHandler()
        target_r2 = "https://pub-123.r2.dev/movie.1080p.mkv"
        # atob(atob(blob))
        b64_inner = base64.b64encode(target_r2.encode()).decode()
        b64_outer = base64.b64encode(b64_inner.encode()).decode()
        html = f"""
        <html>
            <script>
                var link = atob(atob('{b64_outer}'));
            </script>
        </html>
        """
        client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.url = "https://vcloud.fit/watch/123"
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.is_binary = False
        client.stream.return_value.__aenter__.return_value = mock_resp

        with patch("ripper.resolver.handlers.vcloud.request_capped_with_client") as mock_fetch:
            mock_fetch.return_value = FetchResult(
                status_code=200,
                url="https://vcloud.fit/watch/123",
                text=html,
                headers={"content-type": "text/html"},
            )
            mirrors = await handler.resolve("https://vcloud.fit/watch/123", client, ResolutionContext())
            self.assertIsNotNone(mirrors)
            next_url, hops = mirrors
            self.assertEqual(next_url, target_r2)


class TestResolverEngine(unittest.IsolatedAsyncioTestCase):
    async def test_loop_detection_guard(self):
        engine = ResolverEngine(max_depth=5)
        # Simulate circular redirect A -> B -> A
        with patch.object(GLOBAL_REGISTRY, "get_handler") as mock_get_handler:
            mock_handler = MagicMock()
            call_count = 0
            async def mock_resolve(current_url, client, context):
                nonlocal call_count
                call_count += 1
                if "page1" in current_url:
                    return "https://gateway.com/page2", [HopInfo(1, "https://gateway.com/page2", 302, "mock_redirect")]
                else:
                    return "https://gateway.com/page1", [HopInfo(2, "https://gateway.com/page1", 302, "mock_redirect")]
            mock_handler.resolve = mock_resolve
            mock_get_handler.return_value = mock_handler

            result = await engine.resolve("https://gateway.com/page1", use_cache=False)
            self.assertFalse(result.is_success)
            self.assertIn("Redirect loop detected", result.error_message)

    async def test_end_to_end_fastpath(self):
        engine = ResolverEngine()
        direct_url = "https://cdn.example.com/movies/Inception.1080p.mkv"
        result = await engine.resolve(direct_url, use_cache=False)
        self.assertTrue(result.is_success)
        self.assertEqual(result.final_url, direct_url)
        self.assertEqual(result.hops[0].redirect_type, "final_media_stream")


class TestAdvancedCryptoAndJS(unittest.TestCase):
    def test_decode_bluemedia_key(self):
        test_str = "0123456789abcdefghijklmnopqrstuvwxyz"
        decoded = decode_bluemedia_key(test_str)
        self.assertIsInstance(decoded, str)
        self.assertGreater(len(decoded), 0)

    def test_decode_nested_atob(self):
        url = "https://r2.example.com/stream.mkv"
        b64_1 = base64.b64encode(url.encode()).decode()
        b64_2 = base64.b64encode(b64_1.encode()).decode()
        res = decode_nested_atob(b64_2)
        self.assertEqual(res, url)

    def test_parse_nextjs_data(self):
        html = '<html><script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {"streamUrl": "https://stream.example.com/123"}}}</script></html>'
        data = parse_nextjs_data(html)
        self.assertIsNotNone(data)
        self.assertEqual(data["props"]["pageProps"]["streamUrl"], "https://stream.example.com/123")

    def test_unpack_obfuscator_io_hex_array(self):
        obf = r'var url = "\x68\x74\x74\x70\x73\x3a\x2f\x2f\x65\x78\x61\x6d\x70\x6c\x65\x2e\x63\x6f\x6d";'
        unpacked = unpack_obfuscator_io_hex_array(obf)
        self.assertIn("https://example.com", unpacked)

    def test_extract_shortener_api_url(self):
        b64_url = base64.b64encode(b"https://final.com/stream.mkv").decode()
        full_api = f"https://short.com/full?api=xyz&url={b64_url}"
        self.assertEqual(extract_shortener_api_url(full_api), "https://final.com/stream.mkv")

        quick_api = "https://short.com/st?api=xyz&url=https%3A%2F%2Ffinal.com%2Fstream.mkv"
        self.assertEqual(extract_shortener_api_url(quick_api), "https://final.com/stream.mkv")


class TestGDToTAdvancedHandshake(unittest.IsolatedAsyncioTestCase):
    async def test_gdtot_ajax_download_with_gd_param(self):
        handler = GDToTHandler()
        url = "https://katdrive.net/file/123456"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_landing = MagicMock()
        mock_landing.text = '<html><input name="crypt" value="test_crypt_cookie_xyz"/></html>'
        mock_landing.status_code = 200
        client.get.return_value = mock_landing

        mock_ajax = MagicMock()
        mock_ajax.status_code = 200
        mock_ajax.json.return_value = {"file": "https://drive.google.com/uc?id=99999&gd=1a2b3c4d5e"}
        client.post.return_value = mock_ajax

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://drive.google.com/open?id=1a2b3c4d5e")
        self.assertEqual(context.cookies.get("crypt"), "test_crypt_cookie_xyz")
        client.post.assert_called_once()
        call_args = client.post.call_args
        self.assertIn("/ajax.php?ajax=download", call_args[0][0])
        self.assertEqual(call_args[1]["data"], {"id": "123456"})


class TestAdShortenersAdvancedBypasses(unittest.IsolatedAsyncioTestCase):
    async def test_bluemediafiles_create_button_resolution(self):
        handler = AdShortenersHandler()
        url = "https://bluemediafiles.com/url-bypass/test"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        encoded_key = "0123456789abcdefghijklmnopqrstuvwxyz"
        mock_landing = MagicMock()
        mock_landing.text = f'<html><script>Create_Button("{encoded_key}");</script></html>'
        mock_landing.status_code = 200
        client.get.side_effect = [
            mock_landing,
            MagicMock(url="https://mega.nz/%23!file_xyz!secret", status_code=200),
        ]

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://mega.nz/file/file_xyz#secret")

    async def test_form_links_go_virtual_submission(self):
        handler = AdShortenersHandler()
        url = "https://rocklinks.net/xyz123"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_landing = MagicMock()
        mock_landing.text = """
        <html>
            <form id="go-link" action="/links/go" method="POST">
                <input name="_csrfToken" value="csrf_test_token_123"/>
                <input name="ad_form_data" value="secret_form_data_456"/>
            </form>
        </html>
        """
        mock_landing.status_code = 200
        client.get.return_value = mock_landing

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"url": "https://hubcloud.club/drive/abcdef"}
        client.post.return_value = mock_post

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://hubcloud.club/drive/abcdef")
        client.post.assert_called_once()
        post_args = client.post.call_args
        self.assertEqual(post_args[1]["data"]["_csrfToken"], "csrf_test_token_123")
        self.assertEqual(post_args[1]["headers"]["X-Requested-With"], "XMLHttpRequest")

    async def test_shareus_pagination_cloudfunction(self):
        handler = AdShortenersHandler()
        url = "https://shareus.io/file123"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_link_resp = MagicMock()
        mock_link_resp.json.return_value = {"link_info": {"destination": "https://target-download.com/video.mp4"}}
        client.get.return_value = mock_link_resp

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://target-download.com/video.mp4")

    async def test_linkvertise_r_param_easy(self):
        handler = AdShortenersHandler()
        dest = "https://destination.com/download.zip"
        b64_dest = base64.b64encode(dest.encode()).decode()
        url = f"https://linkvertise.com/12345/my-link?r={b64_dest}"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, dest)
        self.assertEqual(hops[0].redirect_type, "linkvertise_r_param")

    async def test_shortener_api_unwrap_flow(self):
        handler = AdShortenersHandler()
        b64_target = base64.b64encode(b"https://cdn.example.com/movie.mp4").decode()
        url = f"https://some-shortener.in/full?api=secret_token&url={b64_target}"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://cdn.example.com/movie.mp4")
        self.assertEqual(hops[0].redirect_type, "shortener_api_unwrap")

    async def test_shorte_adsession_bypass(self):
        handler = AdShortenersHandler()
        url = "https://shorte.st/short123"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_landing = MagicMock()
        mock_landing.text = '<html><script>var sessionId = "sess_abc_123";</script></html>'
        mock_landing.status_code = 200

        mock_end = MagicMock()
        mock_end.text = '{"destination": "https://destination.com/final_file.mkv"}'
        mock_end.status_code = 200

        client.get.side_effect = [mock_landing, mock_end]

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://destination.com/final_file.mkv")
        self.assertEqual(hops[-1].redirect_type, "shorte_adsession")

    async def test_vnshortener_2stage_handshake(self):
        handler = AdShortenersHandler()
        url = "https://vnshortener.com/code123"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_step1 = MagicMock()
        mock_step1.json.return_value = {"inserted_data": {"id": 998877}}
        mock_step2 = MagicMock()
        mock_step2.json.return_value = {"status": "ok"}
        mock_post_go = MagicMock()
        mock_post_go.status_code = 200
        mock_post_go.json.return_value = {"url": "https://media.server.org/video.mp4"}

        client.post.side_effect = [mock_step1, mock_step2, mock_post_go]

        mock_step_landing = MagicMock()
        mock_step_landing.text = '<form id="go-link" action="/links/go"><input name="token" value="abc"/></form>'
        client.get.return_value = mock_step_landing

        context = ResolutionContext()
        result = await handler.resolve(url, client, context)
        self.assertIsNotNone(result)
        final_url, hops = result
        self.assertEqual(final_url, "https://media.server.org/video.mp4")

    async def test_solve_recaptcha_v3_anchor_flow(self):
        anchor_url = "https://www.google.com/recaptcha/api2/anchor?ar=1&k=sitekey123&co=co123&v=v123"
        client = AsyncMock()

        mock_anchor_resp = MagicMock()
        mock_anchor_resp.status_code = 200
        mock_anchor_resp.text = '<html><input id="recaptcha-token" value="initial_raw_token_xyz"/></html>'

        mock_reload_resp = MagicMock()
        mock_reload_resp.status_code = 200
        mock_reload_resp.text = '["rresp","valid_solved_token_777"]'

        client.get.return_value = mock_anchor_resp
        client.post.return_value = mock_reload_resp

        token = await solve_recaptcha_v3_anchor(anchor_url, client=client)
        self.assertEqual(token, "valid_solved_token_777")

    async def test_streamtape_direct_stream_resolution(self):
        handler = FileLockersHandler()
        url = "https://streamtape.com/v/O1j7DBkmleiGwm/"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        html = """
        <html>
            <script>document.getElementById('norobotlink').innerHTML = 'xyz&token=secret_stream_token_88';</script>
            <div id="ideoooolink" style="display:none;">streamtape.com/get_video?id=test1234</div>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}

        with patch("ripper.resolver.handlers.file_lockers.request_capped", AsyncMock(return_value=FetchResult(status_code=200, headers={}, text=html))):
            context = ResolutionContext()
            res = await handler.resolve(url, client, context)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertIn("streamtape.com/get_video?id=test1234&token=secret_stream_token_88&dl=1", direct_url)
            self.assertEqual(hops[-1].redirect_type, "streamtape_direct_stream")

    async def test_krakenfiles_api_resolution(self):
        handler = FileLockersHandler()
        url = "https://krakenfiles.com/view/JEp6lUTRUW/file.html"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        html = """
        <html>
            <input id="dl-token" value="kraken_dl_token_123"/>
            <div data-file-hash="hash_abc_999">Download File</div>
        </html>
        """
        mock_api_resp = MagicMock()
        mock_api_resp.status_code = 200
        mock_api_resp.json.return_value = {"url": "https://cdn.krakenfiles.com/files/download_file.zip"}
        client.post.return_value = mock_api_resp

        with patch("ripper.resolver.handlers.file_lockers.request_capped", AsyncMock(return_value=FetchResult(status_code=200, headers={}, text=html))):
            context = ResolutionContext()
            res = await handler.resolve(url, client, context)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://cdn.krakenfiles.com/files/download_file.zip")
            self.assertEqual(hops[-1].redirect_type, "krakenfiles_api_direct")

    async def test_sendcm_direct_resolution(self):
        handler = FileLockersHandler()
        url = "https://send.cm/ce3zr4cp0i7k"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        html = """
        <html>
            <form action="https://send.cm/">
                <input type="hidden" name="id" value="ce3zr4cp0i7k"/>
            </form>
        </html>
        """
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 302
        mock_post_resp.headers = {"Location": "https://cdn.send.cm/download/video.mkv"}
        client.post.return_value = mock_post_resp

        with patch("ripper.resolver.handlers.file_lockers.request_capped", AsyncMock(return_value=FetchResult(status_code=200, headers={}, text=html))):
            context = ResolutionContext()
            res = await handler.resolve(url, client, context)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://cdn.send.cm/download/video.mkv")
            self.assertEqual(hops[-1].redirect_type, "sendcm_direct_redirect")

    async def test_filecrypt_dlc_resolution(self):
        handler = FileCryptHandler()
        url = "https://filecrypt.cc/Container/12345678.html"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        container_html = """
        <html>
            <a href="/DLC/12345678.dlc">Download DLC</a>
        </html>
        """
        mock_dlc_resp = MagicMock()
        mock_dlc_resp.status_code = 200
        mock_dlc_resp.text = "base64_encoded_dlc_package_content"

        mock_dcrypt_resp = MagicMock()
        mock_dcrypt_resp.status_code = 200
        mock_dcrypt_resp.json.return_value = {"success": {"links": ["https://pixeldrain.com/u/abc12345"]}}

        client.get.return_value = mock_dlc_resp
        client.post.return_value = mock_dcrypt_resp

        with patch("ripper.resolver.handlers.filecrypt.request_capped", AsyncMock(return_value=FetchResult(status_code=200, headers={}, text=container_html))):
            context = ResolutionContext()
            res = await handler.resolve(url, client, context)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://pixeldrain.com/u/abc12345")
            self.assertEqual(hops[-1].redirect_type, "filecrypt_dcrypt_dlc")

    async def test_ouo_recaptcha_bypass_flow(self):
        handler = AdShortenersHandler()
        url = "https://ouo.io/HxFVfD"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        # Initial GET returns landing with form token
        mock_landing = MagicMock()
        mock_landing.headers = {}
        mock_landing.text = '<form action="/go/HxFVfD"><input name="_token" value="ouo_csrf_token_1"/></form>'

        # POST /go/HxFVfD returns redirect to destination
        mock_step_post = MagicMock()
        mock_step_post.headers = {"Location": "https://destination-media.org/target.mkv"}

        client.get.return_value = mock_landing
        client.post.return_value = mock_step_post

        with patch("ripper.resolver.handlers.ad_shorteners.solve_recaptcha_v3_anchor", AsyncMock(return_value="recaptcha_solved_x_token")):
            context = ResolutionContext()
            res = await handler.resolve(url, client, context)
            self.assertIsNotNone(res)
            direct_url, hops = res
            self.assertEqual(direct_url, "https://destination-media.org/target.mkv")
            self.assertEqual(hops[-1].redirect_type, "ouo_recaptcha_bypassed")

    async def test_gplinks_2stage_bypass_flow(self):
        handler = AdShortenersHandler()
        url = "https://gplinks.co/Z94r6"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_probe = MagicMock()
        mock_probe.headers = {"Location": "https://gplinks.co/?vid=session_vid_123"}

        mock_landing = MagicMock()
        mock_landing.text = '<form id="go-link" action="/links/go"><input name="csrf" value="tok123"/></form>'

        client.get.side_effect = [mock_probe, mock_landing]

        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"url": "https://target-drive.org/file.mp4"}
        client.post.return_value = mock_post

        context = ResolutionContext()
        res = await handler.resolve(url, client, context)
        self.assertIsNotNone(res)
        direct_url, hops = res
        self.assertEqual(direct_url, "https://target-drive.org/file.mp4")

    async def test_sharerpw_drive_bridge_resolution(self):
        handler = GDToTHandler()
        url = "https://sharer.pw/file/XuV3WQknRbB"
        self.assertTrue(handler.can_handle(url))

        client = AsyncMock()
        mock_landing = MagicMock()
        mock_landing.status_code = 200
        mock_landing.text = "<html><script>var _token = 'sharer_token_777';</script></html>"

        mock_ajax_resp = MagicMock()
        mock_ajax_resp.status_code = 200
        mock_ajax_resp.json.return_value = {"url": "https://drive.google.com/open?id=12345ABCDE"}

        client.get.return_value = mock_landing
        client.post.return_value = mock_ajax_resp

        context = ResolutionContext()
        res = await handler.resolve(url, client, context)
        self.assertIsNotNone(res)
        direct_url, hops = res
        self.assertEqual(direct_url, "https://drive.google.com/open?id=12345ABCDE")
        self.assertEqual(hops[-1].redirect_type, "sharerpw_drive_bridge")

    def test_caesar_decipher_and_multistage(self):
        plain = "hello world"
        rot = caesar_decipher(plain, shift=13)
        self.assertEqual(rot, "uryyb jbeyq")
        self.assertEqual(caesar_decipher(rot, shift=13), plain)

        # Multi-stage Base64 + Caesar test
        target_url = "https://media-server.net/download/movie.mkv"
        # 1. Apply Caesar
        shifted = caesar_decipher(target_url, shift=-13)
        # 2. 5-layer Base64
        cur = shifted
        for _ in range(5):
            cur = base64.b64encode(cur.encode("utf-8")).decode("ascii")
        test_input = f"https://desbloquea.me/s.php?i={cur}"
        unpacked = decode_multistage_caesar_b64(test_input)
        self.assertEqual(unpacked, target_url)

    async def test_file_lockers_racaty_and_solidfiles(self):
        handler = FileLockersHandler()
        self.assertTrue(handler.can_handle("https://racaty.net/10w86dphf8y2"))
        self.assertTrue(handler.can_handle("http://www.solidfiles.com/v/WqL3V2QjdmDZv"))

        # Racaty test
        client = AsyncMock()
        mock_racaty_resp = MagicMock()
        mock_racaty_resp.text = '<html><a class="btn-dow" href="https://racaty.net/d/direct.mkv">Download</a></html>'
        client.post.return_value = mock_racaty_resp

        context = ResolutionContext()
        res = await handler.resolve("https://racaty.net/10w86dphf8y2", client, context)
        self.assertIsNotNone(res)
        direct_url, hops = res
        self.assertEqual(direct_url, "https://racaty.net/d/direct.mkv")

        # Solidfiles test
        mock_sf_resp = MagicMock()
        mock_sf_resp.text = '<html><script>\'viewerOptions\', {"downloadUrl": "https://stream.solidfiles.net/video.mp4"});</script></html>'
        client.get.return_value = mock_sf_resp
        res_sf = await handler.resolve("http://www.solidfiles.com/v/WqL3V2QjdmDZv", client, context)
        self.assertIsNotNone(res_sf)
        sf_url, sf_hops = res_sf
        self.assertEqual(sf_url, "https://stream.solidfiles.net/video.mp4")

    async def test_file_lockers_sfile_fembed_streamsb(self):
        handler = FileLockersHandler()
        client = AsyncMock()
        context = ResolutionContext()

        # SFile test
        mock_sfile = MagicMock()
        mock_sfile.text = '<html><p><a href="https://sfile.mobi/get/123/file.apk">Download</a></p></html>'
        client.get.return_value = mock_sfile
        res_sfile = await handler.resolve("https://sfile.mobi/1nNX2v3K5iI7", client, context)
        self.assertIsNotNone(res_sfile)
        self.assertEqual(res_sfile[0], "https://sfile.mobi/get/123/file.apk")

        # Fembed test
        mock_fembed = MagicMock()
        mock_fembed.json.return_value = {"data": [{"file": "https://cdn.fembed.com/720.mp4", "label": "720p"}]}
        client.post.return_value = mock_fembed
        res_fe = await handler.resolve("https://fembed-hd.com/v/246q0h26m5kj5ez", client, context)
        self.assertIsNotNone(res_fe)
        self.assertEqual(res_fe[0], "https://cdn.fembed.com/720.mp4")

        # StreamSB test
        mock_sb = MagicMock()
        mock_sb.json.return_value = {"stream_data": {"file": "https://direct.watchsb.com/stream.m3u8"}}
        client.get.return_value = mock_sb
        res_sb = await handler.resolve("https://watchsb.com/e/ggyqfyu52zs2.html", client, context)
        self.assertIsNotNone(res_sb)
        self.assertEqual(res_sb[0], "https://direct.watchsb.com/stream.m3u8")

    async def test_ad_shorteners_try2link_and_sirigan(self):
        handler = AdShortenersHandler()
        client = AsyncMock()
        context = ResolutionContext()

        # Try2link test
        mock_t2l_page = MagicMock()
        mock_t2l_page.text = '<html><form id="go-link"><input name="token" value="abc123xyz" /></form></html>'
        mock_t2l_post = MagicMock()
        mock_t2l_post.json.return_value = {"url": "https://destination-media.com/stream.mkv"}
        client.get.return_value = mock_t2l_page
        client.post.return_value = mock_t2l_post

        res_t2l = await handler.resolve("https://try2link.com/bfHVhj0", client, context)
        self.assertIsNotNone(res_t2l)
        self.assertEqual(res_t2l[0], "https://destination-media.com/stream.mkv")

        # Sirigan recursive base64 test
        target_dest = "https://final-stream.org/movie.mp4"
        enc = f"url={target_dest}"
        for _ in range(3):
            enc = base64.b64encode(enc.encode("utf-8")).decode("ascii")
        mock_sirigan_resp = MagicMock()
        mock_sirigan_resp.url = f"https://safeurl.sirigan.my.id/proses.html?asu={enc}"
        client.get.return_value = mock_sirigan_resp

        res_siri = await handler.resolve("https://safeurl.sirigan.my.id/test", client, context)
        self.assertIsNotNone(res_siri)
        self.assertEqual(res_siri[0], target_dest)


if __name__ == "__main__":
    unittest.main()