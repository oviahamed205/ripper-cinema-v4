# UX / OUTPUT GUIDELINES

## Principle
Errors and output must be concise and actionable, never a raw stack trace or raw provider payload.

Bad:
```
Traceback (most recent call last)...
HTTP 401...
<internal object dump>
```

Good:
```
Authentication failed.
Run: [tool] auth login
```

## Machine-readable mode
Any `--json` / `Accept: application/json` output must be valid, well-formed JSON with a stable schema.

## Consistency
- Use the same terminology across every screen/command/response.
- Same error format everywhere.
- Same success/confirmation format everywhere.
