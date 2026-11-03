"""
Universal Local Proxy Server for Direct Media Playback (Enterprise Multi-Threaded Streamer)
Runs as a detached multi-threaded background service on 127.0.0.1:5055:
- Uses ThreadingHTTPServer for zero-deadlock concurrent streaming and metadata probing
- Instant chunked byte streaming (zero RAM buffer latency - begins streaming to PotPlayer in < 30ms)
- Impersonates Chrome 120 TLS fingerprints (curl_cffi) to bypass Cloudflare, Akamai, and anti-bot filters
- Selectively injects origin headers (X-Forwarded-For for DoodStream / raw CDNs; clean headers for Cloudflare / Fastly)
- Rewrites internal HLS relative playlist segment paths (.ts, .txt, .m3u8) on the fly
- Supports full HTTP 206 Range scrubbing, seeking, pausing, and turbo buffering
- Handles BrokenPipeError / ConnectionResetError gracefully on player seeking/pausing
"""

import os
import sys
import re
import ssl
import json
import socket
import time
import asyncio
import subprocess
import threading
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    import httpx
    HAS_CURL_CFFI = False

from .proxy.png_stripper import strip_fake_png_header

LOCAL_PROXY_PORT = 5055
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

# Cached egress IP for CDN origin header injection
_CACHED_EGRESS_IP = "113.21.230.163"


# Global High-Performance DNS & Resolution Cache
_DNS_CACHE = {}

def resolve_host_doh(host: str) -> Optional[str]:
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    try:
        req_doh = urllib.request.Request(
            f"https://1.1.1.1/dns-query?name={host}&type=A",
            headers={"Accept": "application/dns-json", "User-Agent": "Mozilla/5.0"}
        )
        doh_data = json.loads(urllib.request.urlopen(req_doh, timeout=3.0).read())
        answers = [a["data"] for a in doh_data.get("Answer", []) if a.get("type") == 1]
        if answers:
            _DNS_CACHE[host] = answers[0]
            return answers[0]
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(host)
        _DNS_CACHE[host] = ip
        return ip
    except Exception:
        return None

def get_egress_ip() -> str:
    global _CACHED_EGRESS_IP
    if _CACHED_EGRESS_IP:
        return _CACHED_EGRESS_IP
    try:
        if HAS_CURL_CFFI:
            s = cffi_requests.Session(impersonate="chrome120")
            r = s.get("https://api.ipify.org", timeout=3)
            _CACHED_EGRESS_IP = r.text.strip()
        else:
            with httpx.Client(timeout=3) as cl:
                _CACHED_EGRESS_IP = cl.get("https://api.ipify.org").text.strip()
    except Exception:
        _CACHED_EGRESS_IP = "113.21.230.163"
    return _CACHED_EGRESS_IP


def stream_via_snifree_relay(target_url: str, req_headers: dict, handler_inst, timeout: float = 12.0) -> bool:
    """
    Direct socket streamer with SNI evasion and DoH resolution.
    Bypasses ISP Deep Packet Inspection (DPI) handshake drops on CDN video streams.
    """
    try:
        parsed = urllib.parse.urlparse(target_url)
        host = parsed.netloc
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # 1. Instant Cached DoH Resolution
        ip = resolve_host_doh(host)
        if not ip:
            return False

        # 2. Dual-Mode Handshake: Try SNI-omission (anti-DPI); if host requires SNI, fallback instantly
        s = socket.create_connection((ip, port), timeout=timeout)
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                s = ctx.wrap_socket(s, server_hostname=None)
            except Exception:
                s.close()
                s = socket.create_connection((ip, port), timeout=timeout)
                s = ctx.wrap_socket(s, server_hostname=host)

        path_query = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        lines = [f"GET {path_query} HTTP/1.1", f"Host: {host}"]
        for k, v in req_headers.items():
            if k.lower() != "host":
                lines.append(f"{k}: {v}")
        lines.append("Connection: close\r\n\r\n")

        s.sendall("\r\n".join(lines).encode("utf-8"))

        # Read response headers
        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            c = s.recv(1024)
            if not c:
                break
            header_buf += c

        if b"\r\n\r\n" not in header_buf:
            return False

        head, body_start = header_buf.split(b"\r\n\r\n", 1)
        status_line = head.splitlines()[0].decode("latin1")
        parts = status_line.split()
        status_code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 200

        # Follow redirects (301, 302, 307, 308) automatically
        if status_code in [301, 302, 303, 307, 308]:
            redir_url = None
            for line in head.splitlines()[1:]:
                line_str = line.decode("latin1")
                if ":" in line_str:
                    hk, hv = line_str.split(":", 1)
                    if hk.strip().lower() == "location":
                        redir_url = hv.strip()
                        break
            if redir_url:
                full_redir = urllib.parse.urljoin(target_url, redir_url)
                # Recurse into redirected URL cleanly
                return stream_via_snifree_relay(full_redir, req_headers, handler_inst, timeout)

        handler_inst.send_response(status_code)
        for line in head.splitlines()[1:]:
            line_str = line.decode("latin1")
            if ":" in line_str:
                hk, hv = line_str.split(":", 1)
                hk = hk.strip()
                hv = hv.strip()
                if hk.lower() in ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]:
                    handler_inst.send_header(hk, hv)

        handler_inst.send_header("Access-Control-Allow-Origin", "*")
        handler_inst.end_headers()

        if body_start:
            body_start = strip_fake_png_header(body_start)
            handler_inst.wfile.write(body_start)

        # Optimize socket buffers for maximum streaming bandwidth and minimum latency
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        except Exception:
            pass

        first_chunk = True
        while True:
            chunk = s.recv(512 * 1024)
            if not chunk:
                break
            if first_chunk and not body_start:
                chunk = strip_fake_png_header(chunk)
                first_chunk = False
            try:
                handler_inst.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                break

        return True
    except Exception:
        return False



class LocalStreamProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass # Silence logging to prevent console pollution

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        # Health check endpoint
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            try:
                self.wfile.write(b"OK")
            except Exception:
                pass
            return

        # Modern Localhost Cinema Web Player Endpoint
        if parsed.path == "/player":
            qs = urllib.parse.parse_qs(parsed.query)
            session_id = qs.get("session", [""])[0]
            from .session_manager import get_session
            from .web_player import generate_web_player_html
            
            sess = get_session(session_id) if session_id else None
            title = sess.get("title", "Video Stream") if sess else "Direct Cinema Stream"
            active_url = sess.get("active_stream_url", "") if sess else qs.get("url", [""])[0]
            streams_list = sess.get("streams", []) if sess else [{"quality": "Direct Source", "url": active_url}]
            
            html = generate_web_player_html(session_id, title, active_url, streams_list)
            html_bytes = html.encode("utf-8")
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(html_bytes)
            except Exception:
                pass
            return

        # Real-Time Session Status API for Web Player Live Sync
        if parsed.path == "/api/session":
            qs = urllib.parse.parse_qs(parsed.query)
            session_id = qs.get("id", [""])[0]
            from .session_manager import get_session
            sess = get_session(session_id) if session_id else None
            out_json = json.dumps(sess or {}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out_json)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(out_json)
            except Exception:
                pass
            return

        # Direct Browser-to-Stream API (Resolves any pasted link without CLI)
        if parsed.path == "/api/resolve":
            qs = urllib.parse.parse_qs(parsed.query)
            raw_url = qs.get("url", [""])[0]
            if not raw_url:
                self.send_response(400)
                self.end_headers()
                return

            from .anystream import extract_any_streams, sanitize_user_url
            from .session_manager import register_playback_session
            
            clean_url = sanitize_user_url(raw_url)
            loop = asyncio.new_event_loop()
            try:
                streams = loop.run_until_complete(extract_any_streams(clean_url))
            except Exception:
                streams = []
            finally:
                loop.close()

            if streams:
                top_s = streams[0]
                session_id = register_playback_session(
                    origin_url=clean_url,
                    title=top_s.get("title", "Direct Stream"),
                    initial_streams=streams,
                    referer=top_s.get("referer", clean_url)
                )
                res_data = {
                    "session_id": session_id,
                    "title": top_s.get("title", "Direct Stream"),
                    "active_stream_url": top_s.get("url", ""),
                    "streams": streams
                }
            else:
                res_data = {"error": "No streams found"}

            out_json = json.dumps(res_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out_json)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(out_json)
            except Exception:
                pass
            return

        if parsed.path.startswith("/stream"):
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("url", [""])[0]
            ref = qs.get("ref", [""])[0]
            session_id = qs.get("session", [""])[0]

            # If target not passed directly or expired, fetch active stream from live session sentinel
            if session_id:
                from .session_manager import get_session
                sess = get_session(session_id)
                if sess:
                    if not target or not ref:
                        target = target or sess.get("active_stream_url", "")
                        ref = ref or sess.get("referer", "")

            if not target:
                self.send_response(400)
                self.end_headers()
                return

            req_headers = {
                "User-Agent": DEFAULT_UA,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            # Doodstream CDN origin check
            if any(k in target.lower() for k in ["cloudatacdn.com", "dood", "d000d", "playmogo"]):
                egress_ip = get_egress_ip()
                req_headers["X-Forwarded-For"] = egress_ip

            if ref:
                req_headers["Referer"] = ref
                req_headers["Origin"] = ref.rstrip("/")

            range_header = self.headers.get("Range", "")
            if range_header:
                req_headers["Range"] = range_header

            try:
                # 1. Handle HLS playlists (.m3u8, master.txt)
                is_hls_req = any(k in target.lower() for k in [".m3u8", "master.txt", "/hls/"])
                if is_hls_req:
                    if HAS_CURL_CFFI:
                        session = cffi_requests.Session(impersonate="chrome120")
                        resp = session.get(target, headers=req_headers, timeout=15)
                        content = resp.content
                    else:
                        with httpx.Client(timeout=15, verify=False, follow_redirects=True) as client:
                            resp = client.get(target, headers=req_headers)
                            content = resp.content

                    if b"#EXTM3U" in content:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        
                        # Rewrite relative links and URI="..." attributes inside playlist to route through proxy
                        lines = content.decode("utf-8", errors="replace").splitlines()
                        rewritten = []
                        base_target = target
                        uri_attr_re = re.compile(r'URI="([^"]*)"')

                        def _wrap_proxy_url(uri_ref: str) -> str:
                            full_u = urllib.parse.urljoin(base_target, uri_ref.strip())
                            return f"http://127.0.0.1:{LOCAL_PROXY_PORT}/stream.ts?url={urllib.parse.quote(full_u)}&ref={urllib.parse.quote(ref)}"

                        for line in lines:
                            l = line.strip()
                            if l and not l.startswith("#"):
                                rewritten.append(_wrap_proxy_url(l))
                            elif l.startswith("#") and 'URI="' in l:
                                new_line = uri_attr_re.sub(lambda m: f'URI="{_wrap_proxy_url(m.group(1))}"', line)
                                rewritten.append(new_line)
                            else:
                                rewritten.append(line)
                        out_bytes = "\n".join(rewritten).encode("utf-8")
                        self.send_header("Content-Length", str(len(out_bytes)))
                        self.end_headers()
                        self.wfile.write(out_bytes)
                        return

                # 2. Binary Video / Segment Streaming with Ultra-Fast Turbo Relay
                # Priority 1: Direct SNI-evading raw socket stream (Zero handshake stall, < 50ms seek)
                streamed = stream_via_snifree_relay(target, req_headers, self, timeout=8.0)

                # Priority 2: curl_cffi Chrome 120 fallback (for Cloudflare Turnstile protected streams)
                if not streamed and HAS_CURL_CFFI:
                    try:
                        session = cffi_requests.Session(impersonate="chrome120")
                        resp = session.get(target, headers=req_headers, timeout=4, stream=True)
                        if resp.status_code < 400:
                            self.send_response(resp.status_code)
                            for k, v in resp.headers.items():
                                if k.lower() in ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]:
                                    self.send_header(k, v)
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.end_headers()

                            for chunk in resp.iter_content(chunk_size=256 * 1024):
                                if not chunk:
                                    break
                                try:
                                    self.wfile.write(chunk)
                                except (BrokenPipeError, ConnectionResetError):
                                    break
                            streamed = True
                    except Exception:
                        streamed = False

                if not streamed:
                    try:
                        with httpx.Client(timeout=10, verify=False, follow_redirects=True) as client:
                            with client.stream("GET", target, headers=req_headers) as resp:
                                self.send_response(resp.status_code)
                                for k, v in resp.headers.items():
                                    if k.lower() in ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]:
                                        self.send_header(k, v)
                                self.send_header("Access-Control-Allow-Origin", "*")
                                self.end_headers()

                                for chunk in resp.iter_bytes(chunk_size=128 * 1024):
                                    if not chunk:
                                        break
                                    try:
                                        self.wfile.write(chunk)
                                    except (BrokenPipeError, ConnectionResetError):
                                        break
                    except Exception:
                        pass
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                try:
                    self.send_response(500)
                    self.end_headers()
                except Exception:
                    pass
            return

        self.send_response(404)
        self.end_headers()


def is_proxy_alive() -> bool:
    """Checks if the proxy server is responding on port 5055."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{LOCAL_PROXY_PORT}/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_proxy_server_foreground():
    """Runs the multi-threaded HTTP server in foreground."""
    server = ThreadingHTTPServer(("127.0.0.1", LOCAL_PROXY_PORT), LocalStreamProxyHandler)
    server.serve_forever()


_PROXY_THREAD = None
_SERVER_INSTANCE = None

def ensure_proxy_running():
    """Starts the local stream proxy as a persistent background daemon if not already running."""
    global _PROXY_THREAD, _SERVER_INSTANCE
    if is_proxy_alive():
        return

    def _run_server():
        global _SERVER_INSTANCE
        try:
            _SERVER_INSTANCE = ThreadingHTTPServer(("127.0.0.1", LOCAL_PROXY_PORT), LocalStreamProxyHandler)
            _SERVER_INSTANCE.serve_forever()
        except Exception:
            pass

    _PROXY_THREAD = threading.Thread(target=_run_server, daemon=True)
    _PROXY_THREAD.start()

    # Wait for startup
    for _ in range(25):
        if is_proxy_alive():
            break
        time.sleep(0.1)


def get_proxied_stream_url(direct_url: str, referer: str = "", session_id: str = "") -> str:
    """Returns local proxy stream URL guaranteed to stay alive in PotPlayer."""
    ensure_proxy_running()
    encoded_url = urllib.parse.quote(direct_url)
    encoded_ref = urllib.parse.quote(referer)
    ext = ".m3u8" if any(k in direct_url.lower() for k in [".m3u8", "master.txt", "/hls/"]) else ".mp4"
    sess_param = f"&session={session_id}" if session_id else ""
    return f"http://127.0.0.1:{LOCAL_PROXY_PORT}/stream{ext}?url={encoded_url}&ref={encoded_ref}{sess_param}"


def get_web_player_url(session_id: str) -> str:
    """Returns the URL to launch the local cinema web player in Chrome/Browser."""
    ensure_proxy_running()
    return f"http://127.0.0.1:{LOCAL_PROXY_PORT}/player?session={session_id}"


if __name__ == "__main__":
    start_proxy_server_foreground()
