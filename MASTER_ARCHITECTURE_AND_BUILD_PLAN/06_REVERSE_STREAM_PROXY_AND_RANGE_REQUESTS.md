# ⚡ REVERSE STREAM PROXY & HTTP 206 RANGE REQUESTS
### Zero-Buffering Video Streaming, Scrubbing & Header Injection Architecture

---

## 1. Why a Local Reverse Stream Proxy is Mandatory

When playing movies from protected cloud hosts in PotPlayer, VLC, or Web Browsers, three fatal issues occur if you pass raw CDN links directly:
1. **CORS Violations**: Web browsers block cross-origin MP4/M3U8 requests from external CDN servers.
2. **Missing Anti-Hotlink Headers**: Most media players drop custom `Referer` / `Cookie` headers during redirect chains, triggering `HTTP 403 Forbidden`.
3. **Broken Seek / Scrubbing**: If the server fails to handle byte-range requests, dragging the timeline slider restarts the video from 00:00.

---

## 2. Reverse Proxy Architecture (`unshorten/remote_hub.py`)

The local cinema server runs an asynchronous reverse streaming endpoint at:
`http://localhost:8080/api/stream/{stream_id}`

```
[ PotPlayer / Browser ] 
        │  GET /api/stream/abc1234 (Range: bytes=10485760-)
        ▼
[ Local Stream Proxy (remote_hub.py) ]
        │  1. Injects Referer, User-Agent, and Cookies
        │  2. Translates Range request to Remote CDN
        ▼
[ Remote Video CDN (HubCloud / FastCloud) ]
        │  HTTP 206 Partial Content (Bytes 10485760 - 20971520)
        ▼
[ Local Stream Proxy ] ──(Pipes chunk stream)──► [ PotPlayer / Browser ]
```

---

## 3. Asynchronous Range Request Forwarding Implementation

```python
import httpx
from aiohttp import web

async def stream_proxy_handler(request: web.Request) -> web.StreamResponse:
    stream_id = request.match_info.get("stream_id")
    stream_meta = STREAM_SESSION_MAP.get(stream_id)
    if not stream_meta:
        return web.Response(status=404, text="Stream session expired or invalid")

    target_url = stream_meta["url"]
    headers = {
        "User-Agent": stream_meta.get("user_agent", "Mozilla/5.0..."),
        "Referer": stream_meta.get("referer", target_url),
    }

    # Pass client range request
    client_range = request.headers.get("Range")
    if client_range:
        headers["Range"] = client_range

    async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
        req = client.build_request("GET", target_url, headers=headers)
        res = await client.send(req, stream=True)

        response = web.StreamResponse(
            status=res.status_code,
            headers={
                "Content-Type": res.headers.get("Content-Type", "video/mp4"),
                "Accept-Ranges": "bytes",
                "Content-Range": res.headers.get("Content-Range", ""),
                "Content-Length": res.headers.get("Content-Length", ""),
                "Access-Control-Allow-Origin": "*",
            }
        )
        await response.prepare(request)

        async for chunk in res.aiter_bytes(chunk_size=65536): # 64KB high-speed stream pipe
            await response.write(chunk)

        await response.write_eof()
        return response
```
