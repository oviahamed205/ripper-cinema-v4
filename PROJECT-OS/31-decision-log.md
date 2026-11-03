# ARCHITECTURE DECISION RECORD (ADR)

Copy this block per decision.

```
## ADR-XXX

Title: [decision name]
Status: Proposed / Accepted / Superseded
Date: [YYYY-MM-DD]

Context:
[What situation led to needing this decision?]

Decision:
[What was decided?]

Reason:
- ...
- ...

Alternatives considered:
- ...

Rejected because:
[why the alternatives were not chosen]
```

## ADR-001

Title: [e.g. "Adapter-based integration architecture"]
Status: Accepted
Date: [YYYY-MM-DD]

Context:
The application may need to support multiple external services or providers over time.

Decision:
Use adapter/provider interfaces rather than direct integration calls from the core.

Reason:
- Modularity
- Testability
- Maintainability
- Future extensibility

Alternatives considered:
Direct integration inside the application core.

Rejected because:
Creates tight coupling and makes swapping or adding providers expensive.
