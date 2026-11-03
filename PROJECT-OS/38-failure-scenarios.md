# FAILURE SCENARIOS

Test the system's behavior under:
- External service unavailable
- Network disconnected
- Authentication expired
- Invalid configuration
- Corrupt configuration
- Rate limited
- Timeout
- Malformed / unexpected external response
- Disk unavailable / full
- Permission denied
- Interrupted process (SIGINT/SIGTERM mid-operation)

Expected behavior in every case:
```
Fail safely → Explain the problem → Provide a recovery action → Do not corrupt state → Do not expose secrets
```
