# INTEGRATION / PROVIDER ARCHITECTURE

The application core must not depend directly on a specific external service, library, or vendor. Use an interface/adapter.

## Conceptual Interface
```
Provider
│
├── authenticate()
├── disconnect()
├── listCapabilities()
├── execute(request)
├── stream(request)
├── getStatus()
└── healthCheck()
```

## Rules
Each provider/adapter owns:
- Its own API communication
- Its own authentication
- Its own error translation
- Its own request formatting and response parsing

The application core owns:
- Domain objects
- User experience / interface behavior
- Configuration
- Command / request routing
- Application state
