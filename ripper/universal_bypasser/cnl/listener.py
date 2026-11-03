"""
Click'n'Load 2 (CNL2) Local Port 9666 Listener.
Emulates the JDownloader local HTTP server so that web pages with Click'n'Load buttons
can push encrypted links directly to the Ripper engine.
"""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional
from urllib.parse import parse_qs

from aiohttp import web

from ripper.universal_bypasser.cnl.crypto import CNL2Crypto


class CNL2Listener:
    """Runs a local aiohttp server on 127.0.0.1:9666 emulating JDownloader Click'n'Load 2."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9666,
        on_links_received: Optional[Callable[[List[str]], None]] = None
    ):
        self.host = host
        self.port = port
        self.on_links_received = on_links_received
        self.received_links: List[str] = []
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._setup_routes()

    def _setup_routes(self):
        # Crossdomain policy for Flash / Web browsers
        self._app.router.add_get("/crossdomain.xml", self._handle_crossdomain)
        # JDownloader presence check endpoint
        self._app.router.add_get("/flash/", self._handle_check)
        self._app.router.add_get("/flash/check", self._handle_check)
        # Payload submission endpoint
        self._app.router.add_post("/flash/addcrypted2", self._handle_addcrypted2)
        self._app.router.add_get("/flash/addcrypted2", self._handle_addcrypted2)

    async def _handle_crossdomain(self, request: web.Request) -> web.Response:
        xml = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE cross-domain-policy SYSTEM "http://www.macromedia.com/xml/dtds/cross-domain-policy.dtd">'
            '<cross-domain-policy>'
            '<allow-access-from domain="*" />'
            '</cross-domain-policy>'
        )
        return web.Response(text=xml, content_type="text/xml")

    async def _handle_check(self, request: web.Request) -> web.Response:
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
        return web.Response(text="JDownloader", headers=headers)

    async def _handle_addcrypted2(self, request: web.Request) -> web.Response:
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }

        # Handle POST or GET parameters
        crypted = ""
        jk = ""
        source = ""

        if request.method == "POST":
            post_data = await request.post()
            crypted = post_data.get("crypted", "")
            jk = post_data.get("jk", "")
            source = post_data.get("source", "")
        else:
            crypted = request.query.get("crypted", "")
            jk = request.query.get("jk", "")
            source = request.query.get("source", "")

        if not crypted or not jk:
            return web.Response(text="missing parameters", status=400, headers=headers)

        try:
            urls = CNL2Crypto.decrypt(crypted, jk)
            for u in urls:
                if u not in self.received_links:
                    self.received_links.append(u)

            if self.on_links_received:
                self.on_links_received(urls)

            return web.Response(text="success\r\n", headers=headers)
        except Exception as e:
            return web.Response(text=f"error: {str(e)}", status=500, headers=headers)

    async def start(self):
        """Starts the local listener daemon."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

    async def stop(self):
        """Stops the local listener."""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
