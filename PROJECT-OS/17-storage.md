# STORAGE

## Abstraction
```
Storage
│
├── ConfigStore
├── SessionStore
├── DataStore
└── CredentialReferenceStore
```

The application core should never manipulate raw files/database rows directly — always go through a repository/store interface.

```
Domain Code
   ↓
Repository Interface
   ↓
Concrete Implementation (filesystem / SQLite / Postgres / etc.)
```

This lets storage be swapped (e.g. local file → cloud DB) without touching business logic.
