"""
Comprehensive Unit & Integration Test Suite for Universal Shortlink Bypasser,
Ad-Gate Solvers, Encrypted Containers, and Click'n'Load 2 (CNL2) Decryptor.
"""

import asyncio
import base64
import json
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


@pytest.fixture
def anyio_backend():
    return "asyncio"

from ripper.universal_bypasser.models import (
    BypassContext,
    CNLPayload,
    ContainerResult,
    GateType,
    ShortlinkResult,
)
from ripper.universal_bypasser.classifier import URLClassifier
from ripper.universal_bypasser.cnl.crypto import CNL2Crypto
from ripper.universal_bypasser.cnl.listener import CNL2Listener
from ripper.universal_bypasser.engine import UniversalBypasserEngine
from ripper.universal_bypasser.adgates import (
    GPLinksSolver,
    DroplinkSolver,
    RocklinksSolver,
    OuoSolver,
    GenericFlySolver,
)
from ripper.universal_bypasser.containers import (
    FilecryptUnroller,
    KeeplinksUnroller,
    PastebinUnroller,
    DLCDecoder,
)


class TestURLClassifier:
    """Tests for URL classification and pattern detection."""

    def test_embedded_redirect_extraction(self):
        # Plain query parameter
        url1 = "https://example.com/out?url=https://streamtape.com/v/12345"
        assert URLClassifier.extract_embedded_redirect(url1) == "https://streamtape.com/v/12345"

        # URL-encoded query parameter
        url2 = "https://short.io/go?dest=https%3A%2F%2Fmixdrop.co%2Ff%2Fabcdef"
        assert URLClassifier.extract_embedded_redirect(url2) == "https://mixdrop.co/f/abcdef"

        # Base64 encoded query parameter
        b64_val = base64.b64encode(b"https://doodstream.com/d/xyz987").decode()
        url3 = f"https://wrapper.org/redirect?r={b64_val}"
        assert URLClassifier.extract_embedded_redirect(url3) == "https://doodstream.com/d/xyz987"

        # Classification result
        gate, handler = URLClassifier.classify(url1)
        assert gate == GateType.SIMPLE_REDIRECT
        assert handler == "embedded_param"

    def test_adgate_classification(self):
        cases = [
            ("https://gplinks.co/testslug", GateType.AD_GATE, "gplinks"),
            ("https://droplink.co/sample", GateType.AD_GATE, "droplink"),
            ("https://rocklinks.net/link123", GateType.AD_GATE, "rocklinks"),
            ("https://ouo.io/alpha", GateType.AD_GATE, "ouo"),
            ("https://shrinkme.io/beta", GateType.AD_GATE, "generic_fly"),
        ]
        for u, expected_gate, expected_handler in cases:
            gate, handler = URLClassifier.classify(u)
            assert gate == expected_gate
            assert handler == expected_handler

    def test_container_classification(self):
        cases = [
            ("https://filecrypt.cc/Container/1234ABCD.html", GateType.CONTAINER, "filecrypt"),
            ("https://keeplinks.org/p50/xyz123", GateType.CONTAINER, "keeplinks"),
            ("https://pastebin.com/raw/d84jdf7", GateType.CONTAINER, "pastebin"),
            ("https://linkbox.to/f/folder_id", GateType.CONTAINER, "linkbox"),
        ]
        for u, expected_gate, expected_handler in cases:
            gate, handler = URLClassifier.classify(u)
            assert gate == expected_gate
            assert handler == expected_handler

    def test_direct_hoster_classification(self):
        gate, handler = URLClassifier.classify("https://streamtape.com/v/abcdef/test.mp4")
        assert gate == GateType.DIRECT_HOSTER
        assert handler == "direct_hoster"


class TestCNL2Crypto:
    """Tests for Click'n'Load AES-128-CBC decryption and key extraction."""

    def test_extract_key_from_jk(self):
        # Hex return format
        jk1 = "function f(){ return '0123456789abcdef0123456789abcdef'; }"
        key1 = CNL2Crypto.extract_key_from_jk(jk1)
        assert key1 == bytes.fromhex("0123456789abcdef0123456789abcdef")

        # Double quoted hex
        jk2 = 'return "aabbccddeeff00112233445566778899"'
        key2 = CNL2Crypto.extract_key_from_jk(jk2)
        assert key2 == bytes.fromhex("aabbccddeeff00112233445566778899")

        # 16-byte ASCII key
        jk3 = 'return "1234567890123456"'
        key3 = CNL2Crypto.extract_key_from_jk(jk3)
        assert key3 == b"1234567890123456"

    def test_aes_cbc_full_cycle(self):
        # Generate a known key (16 bytes)
        raw_key = b"16byteSecretKey!"
        iv = raw_key
        jk_code = 'function f(){ return "16byteSecretKey!"; }'

        links = [
            "https://streamtape.com/v/test1",
            "https://doodstream.com/d/test2",
            "https://mixdrop.co/f/test3"
        ]
        plaintext = "\n".join(links).encode("utf-8")

        # Apply PKCS7 padding
        pad_len = 16 - (len(plaintext) % 16)
        padded_plain = plaintext + bytes([pad_len] * pad_len)

        # Encrypt with AES-128-CBC
        cipher = Cipher(algorithms.AES(raw_key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_plain) + encryptor.finalize()
        crypted_b64 = base64.b64encode(ciphertext).decode("ascii")

        # Decrypt using CNL2Crypto
        decrypted_urls = CNL2Crypto.decrypt(crypted_b64, jk_code)
        assert decrypted_urls == links


@pytest.mark.anyio
class TestCNL2Listener:
    """Tests for the local Port 9666 Click'n'Load daemon."""

    async def test_cnl2_listener_endpoints(self):
        import httpx

        received = []
        def on_recv(urls):
            received.extend(urls)

        # Start on port 19666 for unit testing to avoid conflicts
        listener = CNL2Listener(host="127.0.0.1", port=19666, on_links_received=on_recv)
        await listener.start()

        try:
            async with httpx.AsyncClient() as client:
                # 1. Test /flash/check
                r_check = await client.get("http://127.0.0.1:19666/flash/check")
                assert r_check.status_code == 200
                assert "JDownloader" in r_check.text

                # 2. Test /crossdomain.xml
                r_cross = await client.get("http://127.0.0.1:19666/crossdomain.xml")
                assert r_cross.status_code == 200
                assert "cross-domain-policy" in r_cross.text

                # 3. Test /flash/addcrypted2 with valid AES payload
                key = b"A" * 16
                iv = key
                links = ["https://streamtape.com/v/cnl_test_123"]
                plain = "\n".join(links).encode("utf-8")
                pad_len = 16 - (len(plain) % 16)
                padded = plain + bytes([pad_len] * pad_len)

                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                ct = cipher.encryptor().update(padded) + cipher.encryptor().finalize()
                crypted_b64 = base64.b64encode(ct).decode("ascii")
                jk_str = f'return "{key.decode("ascii")}"'

                r_post = await client.post(
                    "http://127.0.0.1:19666/flash/addcrypted2",
                    data={"crypted": crypted_b64, "jk": jk_str}
                )
                assert r_post.status_code == 200
                assert "success" in r_post.text
                assert "https://streamtape.com/v/cnl_test_123" in received
        finally:
            await listener.stop()


@pytest.mark.anyio
class TestUniversalBypasserEngine:
    """Tests for the master orchestrator."""

    async def test_simple_redirect_bypass(self):
        engine = UniversalBypasserEngine()
        target = "https://link-wrapper.com/view?url=https://streamtape.com/v/direct_abc"
        res = await engine.bypass_shortlink(target)
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/direct_abc"
        assert res.solver_used == "embedded_param_unpack"

    async def test_direct_hoster_pass_through(self):
        engine = UniversalBypasserEngine()
        target = "https://mixdrop.co/f/abcde"
        res = await engine.bypass_shortlink(target)
        assert res.success is True
        assert res.resolved_url == target
        assert res.solver_used == "direct_pass"

    async def test_model_serialization(self):
        s_res = ShortlinkResult(
            original_url="https://gplinks.co/x",
            resolved_url="https://streamtape.com/v/1",
            gate_type=GateType.AD_GATE,
            success=True,
            duration=0.15,
            solver_used="gplinks"
        )
        d = s_res.to_dict()
        assert d["gate_type"] == "ad_gate"
        assert d["success"] is True

        c_res = ContainerResult(
            container_url="https://filecrypt.cc/Container/1.html",
            title="Movie Pack",
            unlocked_urls=["https://hoster.com/1", "https://hoster.com/2"],
            success=True,
            duration=0.45
        )
        cd = c_res.to_dict()
        assert cd["total_links"] == 2
        assert len(cd["unlocked_urls"]) == 2


@pytest.mark.anyio
class TestSolversAndContainers:
    """Mock HTTP tests for specific ad-gate and container solvers."""

    async def test_gplinks_solver(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                html = """
                <html><body>
                <form id="go-link" action="/links/go">
                    <input type="hidden" name="alias" value="alpha_slug" />
                    <input type="hidden" name="_wpnonce" value="nonce_abc" />
                </form>
                </body></html>
                """
                return httpx.Response(200, text=html)
            elif request.method == "POST" and "/links/go" in str(request.url):
                return httpx.Response(200, json={"status": "success", "url": "https://streamtape.com/v/gplinks_out"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        solver = GPLinksSolver()
        # Override get_client to use mock transport
        solver.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://gplinks.co/testslug")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/gplinks_out"

    async def test_droplink_solver(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                html = """
                <html><body>
                <form id="link-view" action="/links/go">
                    <input type="hidden" name="csrf" value="drop_csrf_99" />
                </form>
                </body></html>
                """
                return httpx.Response(200, text=html)
            elif request.method == "POST":
                return httpx.Response(200, json={"url": "https://doodstream.com/d/droplink_out"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        solver = DroplinkSolver()
        solver.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://droplink.co/sample")
        assert res.success is True
        assert res.resolved_url == "https://doodstream.com/d/droplink_out"

    async def test_filecrypt_unroller(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "Container" in url_str:
                html = """
                <html><body>
                <h2 class="folder_name">Inception 1080p Pack</h2>
                <a href="/Link/abcd1234efgh5678.html">Mirror 1</a>
                </body></html>
                """
                return httpx.Response(200, text=html)
            elif "Link" in url_str:
                return httpx.Response(302, headers={"Location": "https://streamtape.com/v/inception_streamtape"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        unroller = FilecryptUnroller()
        unroller.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await unroller.unroll("https://filecrypt.cc/Container/1234ABCD.html")
        assert res.success is True
        assert res.title == "Inception 1080p Pack"
        assert "https://streamtape.com/v/inception_streamtape" in res.unlocked_urls

    async def test_pastebin_unroller(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            text = """
            Here are your download links:
            https://mixdrop.co/f/file1
            https://doodstream.com/d/file2
            Enjoy!
            """
            return httpx.Response(200, text=text)

        transport = httpx.MockTransport(handler)
        unroller = PastebinUnroller()
        unroller.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await unroller.unroll("https://pastebin.com/raw/d84jdf7")
        assert res.success is True
        assert len(res.unlocked_urls) == 2
        assert "https://mixdrop.co/f/file1" in res.unlocked_urls
        assert "https://doodstream.com/d/file2" in res.unlocked_urls

    def test_fastforward_declarative_rules(self):
        from ripper.universal_bypasser.adgates.fastforward_rules import FastForwardRules

        # Query parameter rules
        u1 = "https://href.li/?https://streamtape.com/v/target1"
        assert FastForwardRules.match(u1) == "https://streamtape.com/v/target1"

        u2 = "https://go2.pics/?url=https%3A%2F%2Fmixdrop.co%2Ff%2Ftarget2"
        assert FastForwardRules.match(u2) == "https://mixdrop.co/f/target2"

        # Path extraction rules
        u3 = "https://psa.wf/goto/https://doodstream.com/d/target3"
        assert FastForwardRules.match(u3) == "https://doodstream.com/d/target3"

        # Base64 parameter rules
        b64_val = base64.b64encode(b"https://streamtape.com/v/target4").decode()
        u4 = f"https://acortalink.me/?data={b64_val}"
        assert FastForwardRules.match(u4) == "https://streamtape.com/v/target4"

    async def test_sub2unlock_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.sub2unlock import Sub2UnlockSolver

        def handler(request: httpx.Request) -> httpx.Response:
            html = """
            <html><body>
            <button id="unlock-btn" data-target="https://streamtape.com/v/sub2unlock_out">Unlock Link</button>
            </body></html>
            """
            return httpx.Response(200, text=html)

        transport = httpx.MockTransport(handler)
        solver = Sub2UnlockSolver()
        solver.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://sub2unlock.com/sample_id")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/sub2unlock_out"

    async def test_shareus_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.shareus import ShareusSolver

        def handler(request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "/api?shortid=" in url_str:
                return httpx.Response(200, json={"status": True, "link": "https://streamtape.com/v/shareus_out"})
            return httpx.Response(200, text='<html><body><script>var sid = "sid_12345";</script></body></html>')

        transport = httpx.MockTransport(handler)
        solver = ShareusSolver()
        solver.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://shareus.io/?sid=sid_12345")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/shareus_out"

    async def test_cloud_drive_gate_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.cloud_drive_gate import CloudDriveGateSolver

        def handler(request: httpx.Request) -> httpx.Response:
            html = """
            <html><body>
            <script>var download_url = "https://drive.google.com/file/d/12345/view";</script>
            <a class="btn-success" href="https://drive.google.com/file/d/12345/view">Download</a>
            </body></html>
            """
            return httpx.Response(200, text=html)

        transport = httpx.MockTransport(handler)
        solver = CloudDriveGateSolver()
        solver.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://katdrive.net/file/123")
        assert res.success is True
        assert "drive.google.com" in res.resolved_url

    async def test_linkvertise_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.linkvertise import LinkvertiseSolver

        # Test embedded ?r= base64 bypass
        target_b64 = base64.b64encode(b"https://streamtape.com/v/linkvertise_out").decode()
        u = f"https://linkvertise.com/12345/test-slug?r={target_b64}"
        solver = LinkvertiseSolver()
        res = await solver.solve(u)
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/linkvertise_out"

    async def test_psa_wf_solver(self):
        from ripper.universal_bypasser.adgates.psa_wf import PSAWfSolver
        target = "https://streamtape.com/v/final_psa_target"
        u = "https://go2.pics/go2?id=" + base64.b64encode(target.encode()).decode()
        solver = PSAWfSolver()
        res = await solver.solve(u)
        assert res.success is True
        assert res.resolved_url == target

    async def test_try2link_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.try2link import Try2LinkSolver

        def handler(request: httpx.Request) -> httpx.Response:
            if "/links/go" in str(request.url):
                return httpx.Response(200, json={"url": "https://streamtape.com/v/try2link_out"})
            return httpx.Response(200, text='<form action="/links/go"><input name="token" value="xyz"></form>')

        transport = httpx.MockTransport(handler)
        solver = Try2LinkSolver()
        solver.get_client = lambda follow_redirects=True, headers=None: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://try2link.com/test1234")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/try2link_out"

    async def test_bstlar_solver(self):
        import httpx
        from ripper.universal_bypasser.adgates.bstlar import BstlarSolver

        html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"link":{"target_url":"https://streamtape.com/v/bstlar_out"}}}}</script>'
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text=html))
        solver = BstlarSolver()
        solver.get_client = lambda follow_redirects=True, headers=None: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        res = await solver.solve("https://bstlar.com/unlock/testslug")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/bstlar_out"

    async def test_paster_so_solver_and_unroller(self):
        import httpx
        from ripper.universal_bypasser.adgates.paster_so import PasterSoSolver

        paster_html = '<pre class="paste-content">https://streamtape.com/v/file1\nhttps://mixdrop.co/f/file2</pre>'
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text=paster_html))
        solver = PasterSoSolver()
        solver.get_client = lambda follow_redirects=True, headers=None: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        # As single solver
        res = await solver.solve("https://paster.so/paste123")
        assert res.success is True
        assert res.resolved_url == "https://streamtape.com/v/file1"

        # As container unroller
        unroll_res = await solver.unroll("https://paster.so/paste123")
        assert unroll_res.success is True
        assert len(unroll_res.unlocked_urls) == 2
        assert unroll_res.unlocked_urls[1] == "https://mixdrop.co/f/file2"


@pytest.mark.anyio
class TestBackendAutoDetection:
    """Tests for zero-config background auto-detection and bypass across the core pipeline."""

    def test_autodetect_intent_shortener(self):
        from ripper.autodetect import classify_user_input, InputIntent

        # Fastforward link
        p1 = classify_user_input("https://href.li/?https://streamtape.com/v/sample1")
        assert p1.intent == InputIntent.URL_SHORTENER

        # GPLinks ad-gate
        p2 = classify_user_input("https://gplinks.co/myslug")
        assert p2.intent == InputIntent.URL_SHORTENER

        # Filecrypt container
        p3 = classify_user_input("https://filecrypt.cc/Container/1234ABCD.html")
        assert p3.intent == InputIntent.URL_SHORTENER

    async def test_resolver_engine_auto_bypasses_fastforward(self):
        from ripper.resolver import unshorten_url

        url = "https://href.li/?https://streamtape.com/v/auto_bypassed_stream"
        res = await unshorten_url(url)
        assert res.is_success is True
        assert res.final_url == "https://streamtape.com/v/auto_bypassed_stream"
        assert any("shortlink_bypass" in h.redirect_type or "container_unroll" in h.redirect_type for h in res.hops)

    async def test_resolver_engine_auto_bypasses_container(self):
        import httpx
        from ripper.resolver import unshorten_url, ResolverEngine
        from ripper.universal_bypasser import UniversalBypasserEngine
        from ripper.universal_bypasser.containers.pastebin_unroll import PastebinUnroller

        paste_content = "https://streamtape.com/v/file_mirror1\nhttps://mixdrop.co/f/file_mirror2"
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text=paste_content))
        custom_unroller = PastebinUnroller()
        custom_unroller.get_client = lambda follow_redirects=True: httpx.AsyncClient(transport=transport, follow_redirects=follow_redirects)

        u_eng = UniversalBypasserEngine()
        u_eng.container_unrollers["pastebin"] = custom_unroller
        engine = ResolverEngine(universal_engine=u_eng)

        res = await unshorten_url("https://pastebin.com/raw/testcontainer", engine=engine)
        assert res.is_success is True
        assert len(res.server_mirrors) >= 2
        assert any(m.direct_download_url == "https://streamtape.com/v/file_mirror1" for m in res.server_mirrors)


