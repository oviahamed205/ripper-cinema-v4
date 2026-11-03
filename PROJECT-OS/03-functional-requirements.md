# FUNCTIONAL REQUIREMENTS

Use one block per feature area. Adjust freely — this is a starting skeleton, not a fixed list.

## FR-001 [Core capability]
The system must [describe the core thing this project does].

Acceptance:
- [ ] ...
- [ ] ...
- [ ] ...

## FR-002 Authentication (if applicable)
The system provides an authorized authentication mechanism.

Acceptance:
- [ ] User can authenticate.
- [ ] Authentication failures are handled gracefully.
- [ ] Expired authentication is detected and reported.
- [ ] Logout / revoke is supported where applicable.
- [ ] Credentials are never exposed in logs or output.

## FR-003 Configuration
The user can configure supported settings via file, environment variable, or CLI/UI flag.

## FR-004 Error Handling
The system provides useful, human-readable errors without exposing internals or secrets.

## FR-005 Diagnostics
The system provides a way to self-check its own health (e.g. `<tool> doctor`, `/health` endpoint, `npm run diagnose`).
