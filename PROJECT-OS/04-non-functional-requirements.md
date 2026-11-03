# NON-FUNCTIONAL REQUIREMENTS

## Security
- No plaintext secrets in source.
- No sensitive data in logs.
- Principle of least privilege.
- Secure credential storage where applicable.
- Validate and sanitize all external input.

## Reliability
Target: [e.g. 99.x% successful operation under normal supported conditions]

## Performance
Startup / cold-start: Target < [X] ms/s
Normal operation response: Target < [X] seconds excluding third-party latency

## Maintainability
Code must use:
- Clear module boundaries
- Dependency injection where useful
- Typed interfaces (TypeScript / type hints / etc.)
- Documented public APIs

## Portability
Supported platforms: [Windows / Linux / macOS / Browser / iOS / Android — as applicable]

## Accessibility
[UI must remain usable without color / with a screen reader / at 200% zoom — as applicable]

## Observability
Errors should contain an error code, a safe human-readable message, and diagnostic context — never secrets.

## Scalability
Architecture should allow new features/integrations without rewriting the application core.
