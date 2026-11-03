# RISK REGISTER

| ID | Risk | Probability | Impact | Mitigation |
|----|------|-------------|--------|------------|
| R1 | External API changes | Medium | High | Adapter layer isolates change |
| R2 | Authentication failure | Medium | High | Auth abstraction + clear error messaging |
| R3 | Dependency vulnerability | Medium | High | Automated security scanning in CI |
| R4 | Network instability | High | Medium | Retry/backoff strategy |
| R5 | Data leakage | Low | Critical | Secret management + log redaction |
| R6 | [add project-specific risk] | | | |
