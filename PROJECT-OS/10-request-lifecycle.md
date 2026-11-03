# REQUEST LIFECYCLE

```
User Input
    │
    ▼
Input Parser / Router
    │
    ▼
Validation
    │
    ├── invalid ──→ User-facing Error
    │
    ▼
Application Service
    │
    ▼
Integration Adapter
    │
    ▼
Authentication / Authorization Check
    │
    ▼
Request Builder
    │
    ▼
External Service
    │
    ▼
Response Parser
    │
    ▼
Domain Response
    │
    ▼
Output Formatter
    │
    ▼
User-Facing Output
```
