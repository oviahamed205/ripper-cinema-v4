# EXTERNAL INTEGRATION CONTRACT

All external services must sit behind an adapter.

```
External API
     │
     ▼
Adapter (translate + normalize)
     │
     ▼
Normalized Domain Model
     │
     ▼
Application Core
```

The application core must never depend on a raw third-party response shape directly.

## Adapter contract
Every adapter should implement:
```
authenticate()
listCapabilities()
execute(request)
stream(request)
healthCheck()
```

Only integrate through methods a service explicitly and publicly permits (documented APIs / SDKs / OAuth). Never build around bypassing a service's authentication or rate-limit mechanisms.
