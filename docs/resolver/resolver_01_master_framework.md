# ⚡ GOD-TIER RESOLVER: MASTER ARCHITECTURAL SPECIFICATION & SYSTEM FRAMEWORK

---

## 1. System Vision & Architecture Principles

The **Resolver Engine** is an autonomous, deterministic, memory-bounded URL traversal and deobfuscation framework. It resolves intermediate shorteners, countdown traps, JavaScript-obfuscated gates, CAPTCHA hurdles, and file locker mirrors to extract direct, high-speed media stream endpoints (`.mp4`, `.mkv`, `.m3u8`, cloud storage buckets).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              RESOLVER ENGINE ARCHITECTURE                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│   [ Input URL ] ───► [ ResolverEngine.resolve ]                                        │
│                                │                                                       │
│                 ┌──────────────┴──────────────┐                                        │
│                 ▼                             ▼                                        │
│        [ Fast-Path Match ]            [ Intermediate Hop ]                             │
│        (0ms Regex/Direct)                     │                                        │
│                 │                             ▼                                        │
│                 │                     [ CircuitGuard ]                                 │
│                 │                     (Loop / Dead Host)                               │
│                 │                             │                                        │
│                 │                             ▼                                        │
│                 │                   [ Handler Registry ]                               │
│                 │                             │                                        │
│                 │         ┌───────────────────┼───────────────────┐                    │
│                 │         ▼                   ▼                   ▼                    │
│                 │    [AdShorteners]     [FileLockers]      [CloudBridges]              │
│                 │         │                   │                   │                    │
│                 │         └───────────────────┼───────────────────┘                    │
│                 │                             │                                        │
│                 │                             ▼                                        │
│                 │                   [ Core Deobfuscators ]                             │
│                 │                   (Crypto / JS / reCAPTCHA)                          │
│                 │                             │                                        │
│                 │                             ▼                                        │
│                 │                  [ Binary-Safe HTTP/2 ]                              │
│                 │                  (2MB Cap / TLS 1.3 / Chrome)                        │
│                 │                             │                                        │
│                 │                             ▼                                        │
│                 │                  [ Pre-Flight Validator ]                            │
│                 │                  (HTTP 206 Range Probe)                              │
│                 │                             │                                        │
│                 ▼                             ▼                                        │
│             [ UnshortenResult: Direct Verified Playable Media Endpoint ]               │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Layout & Module Responsibilities

```
ripper/resolver/
├── __init__.py                  # Public exports: unshorten_url(), UnshortenResult, ResolverEngine
├── base.py                      # Abstract BaseResolverHandler, ResolutionContext, HopRecord, ServerMirror
├── registry.py                  # Priority-sorted HandlerRegistry with O(1) domain dispatch
├── engine.py                    # Master ResolverEngine orchestrator, loop guard, circuit breaker
│
├── core/                        # Algorithmic, Cryptographic, & Network Primitives
│   ├── __init__.py              # Core module exports
│   ├── binary_safe_http.py      # Size-capped HTTP requests (2MB max HTML, drops video streams)
│   ├── stream_validator.py      # HTTP 206 Range (bytes=0-0) pre-flight probe & mirror latency race
│   ├── circuit_guard.py         # Fast-fail circuit breaker & domain health tracker
│   ├── honeypot_filter.py       # Discards hidden CSS elements & ad-network redirect bait
│   ├── js_unpacker.py           # Dean Edwards Packer, SvelteKit AST, Next.js hydration, Obfuscator.io
│   ├── crypto_unpacker.py       # Rot13, Base64, Hex, cyclic XOR, BlueMedia key, Adfly ysmm, DealDose
│   └── recaptcha_v3.py          # Pure-HTTP Google reCAPTCHA v3 anchor & reload token negotiator
│
└── handlers/                    # 100% Isolated Domain Handlers
    ├── __init__.py              # Auto-registry loader
    ├── cloud_storage.py         # R2, S3, Wasabi, GCS, B2 instant passthrough
    ├── file_lockers.py          # Pixeldrain API, GoFile API, MediaFire, KrakenFiles, Send.cm, Streamtape, Skydrop
    ├── hubcloud.py              # HubCloud, /d/ and /f/ endpoints, GamerXYT generator, R2 streams
    ├── hdhub4u_hubcloud.py      # HDHub4u gateway redirector to HubCloud
    ├── kmhd.py                  # KatMovieHD / links.kmhd.eu SvelteKit AST/JSON unlocker
    ├── vcloud.py                # VegaMovies / V-Cloud atob() token unpacker, FastDL streams
    ├── vegamovies_vcloud.py     # Backward-compatible V-Cloud alias
    ├── magiclinks.py            # MagicLinks countdown timer & Pixeldrain API redirector
    ├── nexdrive.py              # NexDrive form submission automation
    ├── olamovies.py             # OlaMovies multi-hop gateway unwrapper
    ├── gdtot.py                 # GDToT, KatDrive, DriveFire, Kolop, Sharer.pw /ajax.php crypt handshake
    ├── appdrive.py              # AppDrive, JioDrive, DriveHub, DriveSeed token resolvers
    ├── ad_shorteners.py         # Rocklinks, Droplink, Try2Link, Ouo, BlueMedia, Shareus, Adfly, Shorte, GPLinks
    ├── filecrypt.py             # FileCrypt container extractor & dcrypt.it DLC decryptor
    ├── article_crawler.py       # Intermediate download page & movie article multi-hop crawler
    └── universal_heuristics.py  # HTTP 3xx Location, HTML Meta-Refresh, JS window.location fallback
```

---

## 3. The 10-Layer Defense Matrix

| Layer | Name | Description & Mechanics |
|---|---|---|
| **L1** | **Deterministic Fast-Path** | Immediate regex matching for direct media formats (`.mp4`, `.mkv`, `.m3u8`, `.mpd`) and pre-signed storage endpoints (S3, R2, Wasabi, GCS). Bypasses the network stack entirely in **0.01ms**. |
| **L2** | **Deobfuscation & Decryption** | Pure-Python decryption routines for Dean Edwards packer, Adfly `ysmm`, cyclic XOR, DealDose reverse Base64, and nested `atob()` wrappers. |
| **L3** | **Specialized Domain Handlers** | Over 20 isolated handlers targeting specific gateway workflows (HubCloud, GDToT, KMHD, Skydrop, V-Cloud, Streamtape). |
| **L4** | **Pure-HTTP Token Negotiator** | Direct HTTP exchange with Google reCAPTCHA v3 `/anchor` and `/reload` endpoints. Retrieves valid `rresp` tokens without headless browser overhead. |
| **L5** | **Virtual Form Simulation** | Dispatches simulated AJAX form posts (`#go-link`, `_csrfToken`, multipart forms) with correct HTTP headers (`X-Requested-With`, `Referer`, `Origin`). |
| **L6** | **Anti-Bot Resistance** | Uses TLS 1.3 fingerprint matching (Chrome 124 JA3/JA4) and HTTP/2 multiplexing via `curl_cffi` to prevent connection drops. |
| **L7** | **Binary-Safe Stream Capping** | Caps scraped HTML at 2MB (`request_capped`) and immediately drops incoming binary streams upon reading MIME headers to protect system memory. |
| **L8** | **Pre-Flight Stream Verification** | Probes destination URLs with HTTP `Range: bytes=0-0` (HTTP 206 Partial Content) to verify that streams are active before returning. |
| **L9** | **Honeypot Annihilation** | Filters out hidden DOM elements (`opacity:0`, `visibility:hidden`, `position:absolute; left:-9999px`) and ad-network redirection bait. |
| **L10** | **Circuit Breaker & Observability** | Enforces a 25-hop maximum loop limit, tracks visited URLs to stop circular paths, and fast-fails dead domains via sliding error windows. |

---

## 4. Key Data Structures (`models.py`)

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class HopRecord:
    url: str
    handler_name: str
    status_code: int
    duration_ms: float
    extracted_urls: List[str] = field(default_factory=list)

@dataclass
class ServerMirror:
    name: str
    url: str
    priority: int
    quality_label: Optional[str] = None
    is_working: bool = True

@dataclass
class UnshortenResult:
    original_url: str
    resolved_url: str
    is_success: bool = True
    hops: List[HopRecord] = field(default_factory=list)
    mirrors: List[ServerMirror] = field(default_factory=list)
    total_time_ms: float = 0.0
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.is_success

    @property
    def error(self) -> Optional[str]:
        return self.error_message
```

---

## 5. Summary of Built-in Handlers

- **Streamtape**: Scrapes `norobotlink` inner HTML and `div#ideoooolink` to build `https:/{host}&token={tok}&dl=1`.
- **KrakenFiles**: Scrapes `input#dl-token` and `div[data-file-hash]`, POSTs to `/download/{hash}` for direct CDN URLs.
- **Skydrop**: 4-stage automated state handshake (`GET` $\rightarrow$ `POST /resolve/` $\rightarrow$ `GET /id/` $\rightarrow$ `POST /fetch/` $\rightarrow$ 302).
- **Ouo.io / Ouo.press**: Combines reCAPTCHA v3 anchor tokens with two-step `/go/` and `/xreallcygo/` form submissions.
- **GPLinks**: Handles 302 query extraction (`?{vid}`), referrer spoofing (`mynewsmedia.co`), and `#go-link` form submission.
- **FileCrypt**: DLC container download and automated `dcrypt.it` API parsing.
- **GDToT / Sharer.pw**: Session cookie extraction and AJAX `/dl` endpoint handshakes.
