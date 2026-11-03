# SECURITY MODEL

## Threat Model
Protect against:
- Credential leakage
- Malicious/malformed input
- Dependency compromise (supply chain)
- Man-in-the-middle attacks
- Unauthorized access to integrations
- Log leakage of sensitive data
- Configuration leakage
- Malicious plugins / extensions (if the project supports them)
- Injection (command, SQL, path traversal, etc.)
- Unsafe file access

## Trust Boundaries
```
┌───────────────────────────────┐
│              USER              │
└───────────────┬───────────────┘
                │
         UNTRUSTED INPUT
                │
                ▼
┌───────────────────────────────┐
│        INTERFACE LAYER         │
└───────────────┬───────────────┘
                │
          VALIDATION
                │
                ▼
┌───────────────────────────────┐
│       APPLICATION CORE         │
└───────────────┬───────────────┘
                │
         INTEGRATION BOUNDARY
                │
                ▼
┌───────────────────────────────┐
│       EXTERNAL SERVICE         │
└───────────────────────────────┘
```

## Secret Handling Rules
Never log: API keys, passwords, cookies, session tokens, authorization headers, private identifiers.

Redact sensitive values in any output, e.g.:
```
sk-************
```

Only integrate with third-party services through methods they officially and explicitly permit (published APIs, documented auth flows). Do not design features around extracting, replaying, or circumventing another service's private session/credential mechanisms.
