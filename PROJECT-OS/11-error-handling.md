# ERROR HANDLING

## Error Taxonomy
```
ApplicationError
│
├── ConfigurationError
├── AuthenticationError
├── AuthorizationError
├── NetworkError
├── IntegrationError
├── ValidationError
├── TimeoutError
├── RateLimitError
├── StorageError
└── InternalError
```

## Error Pipeline
```
External Error
      │
      ▼
Adapter (translate to domain error)
      │
      ▼
Normalized ApplicationError
      │
      ▼
Application Layer (decide: retry? surface? log?)
      │
      ▼
User-Friendly Message
```

Example — instead of surfacing `HTTP 401 Unauthorized: {...}`, show:
```
Authentication failed.
Run: <tool> auth login
```

Detailed diagnostic information should only appear in debug/verbose mode and must never include secrets.
