# DATA MODEL

Define every entity the system persists or passes around. Copy this block per entity.

## [EntityName]
- id
- field
- field
- created_at
- updated_at

## Example — UserConfig
- provider
- preferences
- output_mode

## Example — AuthenticationState
- provider
- authenticated (bool)
- expires_at
- credential_reference   (never store raw secrets directly on domain objects — store a reference to a secure store)

## Example — Session
- id
- created_at
- updated_at
- items[]

## Relationships
```
User
 │
 ├── Config
 │
 └── Sessions
        │
        ▼
   [Domain Entity]
        │
        ▼
     [Child Entity]
```
