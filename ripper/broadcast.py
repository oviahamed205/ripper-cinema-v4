"""
LAN Broadcast Server: Streams movies on local network via a lightweight video proxy.
"""
import http.server
import socketserver
import urllib.parse
import threading
import socket
import httpx
import re
from rich.panel import Panel
from rich import box
from .ui import console

BROADCAST_PORT = 5060
active_stream_url = ""
active_stream_title = ""

class LANBroadcastHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Reverse Proxy supporting video streaming range requests."""
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        global active_stream_url, active_stream_title
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LAN Movie Broadcast: {active_stream_title}</title>
    <style>
        body {{ font-family: sans-serif; background: #0f0f0f; color: #fff; text-align: center; padding: 20px; }}
        video {{ width: 100%; max-width: 800px; border-radius: 8px; border: 2px solid #333; background: #000; margin-top: 20px; }}
        .header {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📡 LAN Live Broadcast</h1>
        <h3>Now Streaming: {active_stream_title or "Movie / Series"}</h3>
    </div>
    <video controls autoplay preload="metadata">
        <source src="/stream" type="video/mp4">
        Your browser does not support HTML5 video streaming.
    </video>
</body>
</html>"""
            self.wfile.write(html.encode("utf-8"))
            return

        if parsed.path == "/stream":
            if not active_stream_url:
                self.send_response(404)
                self.end_headers()
                return

            # Read range header from client
            range_header = self.headers.get("Range", "")
            req_headers = {"User-Agent": "Mozilla/5.0"}
            if range_header:
                req_headers["Range"] = range_header

            try:
                # Forward to target direct stream URL
                with httpx.stream("GET", active_stream_url, headers=req_headers, follow_redirects=True, timeout=12.0) as resp:
                    self.send_response(resp.status_code)
                    # Copy header parameters
                    for k, v in resp.headers.items():
                        if k.lower() in ["content-type", "content-length", "content-range", "accept-ranges"]:
                            self.send_header(k, v)
                    self.end_headers()

                    # Stream chunks back to client
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        try:
                            self.wfile.write(chunk)
                        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                            break  # Client disconnected
            except Exception as e:
                try:
                    self.send_response(500)
                    self.end_headers()
                except Exception:
                    pass
            return

        self.send_response(404)
        self.end_headers()


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


_server_instance = None
_server_thread = None

def start_broadcast_server(stream_url: str, movie_title: str):
    """Start local network broadcast streaming server with automatic port fallback."""
    global active_stream_url, active_stream_title, _server_instance, _server_thread, BROADCAST_PORT
    active_stream_url = stream_url
    active_stream_title = movie_title

    if _server_instance is None:
        candidate_ports = [BROADCAST_PORT] + list(range(8888, 8920)) + list(range(8000, 8020)) + [0]
        seen = set()
        for p in candidate_ports:
            if p in seen:
                continue
            seen.add(p)
            try:
                _server_instance = ThreadingHTTPServer(("", p), LANBroadcastHandler)
                BROADCAST_PORT = _server_instance.server_address[1]
                break
            except OSError:
                continue

        if _server_instance:
            _server_thread = threading.Thread(target=_server_instance.serve_forever)
            _server_thread.daemon = True
            _server_thread.start()

    local_ip = get_local_ip()
    console.print(Panel(
        f"[bold green]📡 LAN Broadcast Server Active![/bold green]\n\n"
        f"🎬 Now Streaming: [bold white]{movie_title}[/bold white]\n"
        f"🔗 Share this link with anyone on your local network/Wi-Fi to watch:\n"
        f"[bold bright_yellow]http://{local_ip}:{BROADCAST_PORT}/[/bold bright_yellow]\n\n"
        f"[dim]They can open this URL on their phones, smart TVs, tablets, or laptops to stream in sync![/dim]\n\n"
        f"[bold red]⚠️ Firewall Tip:[/bold red] If other local devices cannot connect, make sure to allow port [bold yellow]{BROADCAST_PORT}[/bold yellow] in Windows Defender Firewall.",
        title="[bold bright_magenta]LAN VIDEO BROADCAST[/bold bright_magenta]",
        box=box.ROUNDED,
    ))
