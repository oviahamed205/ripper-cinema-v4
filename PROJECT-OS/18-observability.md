# OBSERVABILITY

## Logging levels
```
ERROR
WARN
INFO
DEBUG
TRACE
```
Default: `INFO`. Verbose mode: `[tool] --verbose` or `DEBUG=1`.

Never log secrets. Redact before logging.

## Metrics (track where relevant)
- Command/request execution time
- External call latency
- Request count
- Error count
- Retry count
- Rate-limit events

Do not collect more personal information than the feature genuinely needs.

## Diagnostic command
```
[tool] doctor
```
Checks: installation, configuration, authentication, network, integration connectivity, storage, permissions, dependency health.
