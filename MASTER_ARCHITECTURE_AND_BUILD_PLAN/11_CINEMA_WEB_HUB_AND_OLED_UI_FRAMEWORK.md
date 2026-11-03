# 🖥️ CINEMA WEB HUB & OLED UI FRAMEWORK
### Zero-Latency Responsive Dashboard, Local Cast & Streaming Web Application

---

## 1. Web Hub Architecture Overview

The Cinema Web Hub runs an embedded `aiohttp` / `asyncio` server on port `8080` (`http://localhost:8080`) providing:
1. **Interactive Multi-Site Search Bar**: Auto-completing search querying 20+ movie networks simultaneously.
2. **Neon Glowing Provider Badges**: Distinct glowing badges for VegaMovies, KatmovieHD, CineFreak, OlaMovies, KMmovies, HDHub4u, BollyFlix.
3. **Multi-Source Result Deduplication**: Groups identical movies into a single poster card with a multi-source selector badge (e.g. `VegaMovies +2`).
4. **Embedded VideoJS Player with Range Scrubbing**: Plays 1080p/4K streams directly in browser with subtitle selection.
5. **1-Click Launch PotPlayer / VLC**: Trigger native Windows media player with 1 click from the web UI.

---

## 2. API Endpoints Catalog

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | `GET` | Main Cinema Web Hub Dashboard |
| `/api/search?q={query}` | `GET` | Async multi-site search with TMDB poster enrichment |
| `/api/resolve` | `POST` | Resolves target movie page into direct streamable/download links |
| `/api/stream/{stream_id}` | `GET` | HTTP 206 Range Reverse Stream Proxy for zero-buffering playback |
| `/api/play/potplayer` | `POST` | Spawns native local PotPlayer executable with subtitle args |
| `/api/download` | `POST` | Enqueues multi-part chunked download in background manager |
| `/api/subtitles?q={title}` | `GET` | Queries SubDL & OpenSubtitles for synchronized `.srt` tracks |
| `/api/cast/devices` | `GET` | Auto-detects DLNA / Smart TV cast targets on local Wi-Fi |

---

## 3. UI Color Palette & OLED True Black Theme

```css
:root {
    --bg-oled: #000000;
    --surface-1: #0e0e10;
    --surface-2: #18181b;
    --surface-card: #1f1f23;
    --accent-neon-cyan: #00f2fe;
    --accent-neon-purple: #9d4edd;
    --badge-vegamovies: #00f2fe;
    --badge-katmoviehd: #ff007f;
    --badge-cinefreak: #00ff88;
    --badge-olamovies: #ffaa00;
    --badge-kmmovies: #aa00ff;
    --badge-hdhub4u: #ff3333;
    --badge-bollyflix: #ffff00;
}
```
