# SYSTEM ARCHITECTURE

## High-Level Architecture

```
                    ┌───────────────────┐
                    │       USER         │
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │   INTERFACE LAYER  │   (cli.py & interactive.py)
                    └─────────┬─────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │  APPLICATION CORE  │   (resolver.py & batch.py)
                    └─────────┬─────────┘
                              │
               ┌──────────────┼──────────────┐
               │              │              │
               ▼              ▼              ▼
        ┌────────────┐ ┌────────────┐ ┌────────────┐
        │  Media     │ │  Safety    │ │  Models    │
        │  Parser    │ │  Analyzer  │ │  (Data)    │
        │ (media.py) │ │(safety.py) │ │(models.py) │
        └────────────┘ └────────────┘ └────────────┘
               │              │              │
               └──────────────┼──────────────┘
                              ▼
                    ┌───────────────────┐
                    │  INTEGRATION LAYER │   (External Interfaces)
                    └─────────┬─────────┘
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
       ┌───────────┐    ┌───────────┐    ┌───────────┐
       │  Player   │    │Downloader │    │  Search   │
       │ Integrator│    │  Engine   │    │ Aggregator│
       │(player.py)│    │(download) │    │(search.py)│
       └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
             │                │                │
             ▼                ▼                ▼
         PotPlayer/VLC   Local Disk       External Web
          (Streaming)    (Downloads)      (Movie Portals)
```

## Description of Layers

1. **Interface Layer**:
   - `unshorten/cli.py` handles input options and command routing.
   - `unshorten/interactive.py` displays terminal menus, interactive lists, action prompts, and live tables.
2. **Application Core**:
   - `resolver.py` resolves redirect chains recursively.
   - `batch.py` implements async semaphore loops to speed up bulk execution.
3. **Integration Layer**:
   - `player.py` spawns subprocesses for media players.
   - `downloader.py` leverages HTTP range requests.
   - `search.py` performs requests using BeautifulSoup.
