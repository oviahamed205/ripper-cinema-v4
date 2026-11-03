# APPLICATION STATE MACHINE

```
             ┌──────────────┐
             │   STARTING   │
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ INITIALIZING │
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │    READY     │
             └──────┬───────┘
                    │
             action triggered
                    │
                    ▼
             ┌──────────────┐
             │ PROCESSING   │
             └──────┬───────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
     ┌──────────┐        ┌──────────┐
     │ SUCCESS  │        │  ERROR   │
     └────┬─────┘        └────┬─────┘
          │                   │
          └─────────┬─────────┘
                    ▼
                 READY

Fatal failure
      │
      ▼
   EXITING
      │
      ▼
   TERMINATED
```

Adapt states to match the real lifecycle of the application (e.g. add PAUSED, RECONNECTING, DEGRADED as needed).
