# 🌐 MULTI-SITE HUNTER & DYNAMIC DNS ENGINE
### Real-Time Domain Drift Auto-Detection, Mirror Rotation & Anti-Censorship

---

## 1. The Dynamic Domain Discovery Engine

To ensure that the search engine never goes offline when sites switch domains, the **Site Hunter Subsystem (`unshorten/domains.py`)** employs a 4-tier discovery waterfall:

```
Tier 1: Local Domain Cache (~/.unshorten/domains.json)
        ↓ (If status != 200 or timeout > 2.5s)
Tier 2: Cloudflare DNS-over-HTTPS (DoH) & TXT Record Lookup
        ↓ (If domain changed)
Tier 3: Dynamic Search / Dork Probe (site:<provider_name>.*)
        ↓ (If blocked by Cloudflare)
Tier 4: Telegram / RSS Status Channel Mirror Scraper
```

---

## 2. Supported Provider Registry

| Provider Key | Canonical Name | Primary TLD Mirror | Backup Mirror | CMS Type |
|---|---|---|---|---|
| `vegamovies` | VegaMovies | `vegamovies.skin` | `vegamovies.mex` | WordPress REST + Custom Links |
| `katmoviehd` | KatmovieHD | `katmoviehd.mom` | `katmoviehd.pm` | Custom BlogEngine + GDToT |
| `cinefreak` | CineFreak | `cinefreak.net` | `cinefreak.co` | WordPress + Direct HubCloud |
| `olamovies` | OlaMovies | `olamovies.top` | `olamovies.ink` | WordPress + FastCloud |
| `kmmovies` | KMmovies | `kmmovies.cool` | `kmmovies.vip` | WordPress + FileLions |
| `hdhub4u` | HDHub4u | `hdhub4u.ms` | `hdhub4u.re` | WordPress + HubCloud |
| `bollyflix` | BollyFlix | `bollyflix.zip` | `bollyflix.dad` | WordPress + KatDrive |
| `fmoviess` | FMoviess | `fmoviess.org` | `fmovies.to` | Next.js / Cloudflare Stream |
| `movie4k` | Movie4K | `movie4kto.xyz` | `movie4k.org` | WordPress + StreamTape |
| `lookmovie` | LookMovie | `lookmovie2.city` | `lookmovie.io` | Custom REST API |
| `mp4gana` | Mp4Gana | `mp4gana.com` | `mp4gana.net` | Direct Indexer |
| `7starhd` | 7StarHD | `7starhd.latino` | `7starhd.city` | WordPress + HubCloud |
| `hindilinks4u` | HindiLinks4u | `hindilinks4u.estate` | `hindilinks4u.to` | WordPress + Direct Embed |
| `worldfree4u` | WorldFree4u | `worldfree4u.gd` | `worldfree4u.lol` | WordPress + FastCloud |
| `9xmovie` | 9XMovieLive | `9xmovielive.com` | `9xmovies.click` | WordPress + Direct Stream |
| `downloadhub` | DownloadHub | `downloadhub.ac` | `d8hub.com` | WordPress + Multi-Quality Hub |

---

## 3. Anti-Censorship & DoH Engine
* **DNS-over-HTTPS (DoH)**: Resolves hostnames directly via `https://cloudflare-dns.com/dns-query` (Cloudflare 1.1.1.1) and `https://dns.google/resolve` (Google 8.8.8.8) using encrypted TLS, bypassing ISP DNS hijacking.
* **Auto-Fallback**: If Cloudflare blocks the user's IP, the engine routes requests through ScraperAPI or free Cloudflare Edge Worker relays.
