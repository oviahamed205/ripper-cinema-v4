# 📐 MASTER SYSTEM ARCHITECTURE & DATA FLOW SPECIFICATION
### Complete End-to-End Execution Lifecycles for Search, Resolution, Playback & Downloads

---

## 1. The Search & Metadata Pipeline Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant CLI as CLI / Interactive UI
    participant Search as Search Engine (search.py)
    participant Hunter as Domain Hunter (domains.py)
    participant Providers as 20+ Movie Providers
    participant TMDB as TMDB / TVmaze API

    User->>CLI: Enter Query (e.g. "Spider-Man No Way Home 1080p")
    CLI->>Search: execute_multi_site_search(query)
    Search->>Hunter: get_active_domains()
    Hunter-->>Search: Active Domains (Vega, Katmovie, CineFreak...)
    
    par Parallel Provider Queries
        Search->>Providers: Query WordPress REST API / HTML Search
        Providers-->>Search: Raw Search Results (Title, URL, Quality)
    end

    Search->>Search: Fuzzy Filter, Deduplicate & Score Relevance
    
    par Parallel Metadata Enricher
        Search->>TMDB: extract_clean_movie_title() & fetch_poster()
        TMDB-->>Search: High-Res Poster URL, Backdrop, Rating
    end

    Search-->>CLI: Unified Deduplicated Movie Cards with Glowing Badges
    CLI-->>User: Render Interactive Selection Grid
```

---

## 2. The Link Resolution & Unshortening Pipeline Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant CLI as CLI
    participant Resolver as Link Resolver (resolver.py)
    participant CloudHost as Video Cloud Host (HubCloud / StreamTape)
    participant Deobf as JS Deobfuscator
    participant StreamProxy as Local Stream Proxy

    User->>CLI: Select Movie Card & Quality (1080p / 4K / 720p)
    CLI->>Resolver: resolve_movie_links(page_url)
    Resolver->>Resolver: Extract intermediate shortener links (GPLinks, Droplink...)
    Resolver->>Resolver: Execute bypass algorithms (cookie extraction, form payload generation)
    Resolver->>CloudHost: Handshake with Video Host (HubCloud, FastCloud, GDToT)
    CloudHost-->>Resolver: Obfuscated HTML containing packed JS
    Resolver->>Deobf: unwrap_packed_js(html)
    Deobf-->>Resolver: Direct MP4 / M3U8 Stream URL + Auth Headers
    Resolver->>StreamProxy: register_stream_tunnel(direct_url, headers)
    StreamProxy-->>CLI: Local Stream Endpoint (http://localhost:8080/stream/12345)
    CLI-->>User: Play in PotPlayer or Download
```

---

## 3. The Stream Scrubbing (HTTP 206 Partial Content) Pipeline Flow

```mermaid
sequenceDiagram
    autonumber
    participant PotPlayer as PotPlayer / VLC
    participant LocalProxy as Local Stream Proxy (remote_hub.py)
    participant RemoteCDN as Remote Cloud CDN

    PotPlayer->>LocalProxy: GET /stream/12345 (Range: bytes=0-)
    LocalProxy->>RemoteCDN: GET /video.mp4 (Range: bytes=0-1048576, Referer: host.com)
    RemoteCDN-->>LocalProxy: HTTP 206 Partial Content (Bytes 0-1048576)
    LocalProxy-->>PotPlayer: Stream initial chunk (Playback starts immediately)

    Note over PotPlayer: User drags scrub bar to 45:00 (Byte 1,500,000,000)
    PotPlayer->>LocalProxy: GET /stream/12345 (Range: bytes=1500000000-)
    LocalProxy->>RemoteCDN: GET /video.mp4 (Range: bytes=1500000000-1501048576)
    RemoteCDN-->>LocalProxy: HTTP 206 Partial Content
    LocalProxy-->>PotPlayer: Stream 45:00 timestamp chunk (Zero buffering delay)
```
