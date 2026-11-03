# COMPONENT DEPENDENCY GRAPH

```
Interface Layer (CLI / UI / API)
 │
 ▼
Request / Command Layer
 │
 ▼
Application Services
 │
 ├──────────────┐
 ▼              ▼
Domain Service   Domain Service
 A               B
 │              │
 └──────┬───────┘
        ▼
 Integration Interface
        │
 ┌──────┼────────┐
 ▼      ▼        ▼
 API-A  API-B    API-C
```

Infrastructure (cross-cutting, used by everything above):
```
Config ─────────────┐
Logging ────────────┤
Storage ────────────┤
Networking ─────────┤
Secrets ────────────┤
                     ▼
              Application Core
```

Replace the placeholder boxes with the project's real components once architecture is finalized, and keep this graph in sync with the code.
