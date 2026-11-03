# RESILIENCE

Retry only errors that are safe to retry:
- Temporary network failure
- Timeout
- Temporary service unavailable (5xx)
- Rate limiting (respect `Retry-After`)

Do NOT blindly retry:
- Invalid authentication (fail fast, prompt re-auth)
- Invalid/malformed request (fix, don't retry)
- Permission failure
- Malformed configuration

Use exponential backoff + jitter + a maximum retry count.

```
Attempt 1 → wait → Attempt 2 → wait longer → Attempt 3 → fail safely
```
