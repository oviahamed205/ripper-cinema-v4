# PROJECT-OS

This directory is the authoritative engineering specification for the project.
An AI coding agent (or a human) should treat these documents as the source of
truth before making architectural or implementation decisions.

```
Requirement → Design → Implementation → Test → Verification
```

## How to use this on a brand-new project

Don't hand an agent all 40+ files at once and say "build everything" — that's
how you get 30 conflicting files and a rewrite two weeks later. Go in order:

```
1. Project idea
2. 00-project-charter.md
3. 02/03/04 — requirements
4. 05/06/07 — architecture
5. 08 — data model
6. 12 — security model
7. 30 — task breakdown (first few tasks only)
8. Implement task 1 → test → verify
9. Implement task 2 → test → verify
   ...
10. Testing pass (20/21/22)
11. Security review (12, 32)
12. Final verification (39)
13. Release (35/36)
```

Fill in the placeholders in each file as you go — most files start as a
skeleton with `[PLACEHOLDER]` markers and example content to delete or adapt.

## File index

| File | Purpose |
|---|---|
| 00-project-charter.md | Problem, users, goals, constraints |
| 01-ai-agent-operating-system.md | Rules for the coding agent |
| 02-product-requirements.md | PRD format + requirements |
| 03-functional-requirements.md | Feature-level requirements |
| 04-non-functional-requirements.md | Security, performance, reliability, etc. |
| 05-system-architecture.md | High-level architecture diagram |
| 06-integration-architecture.md | How external services/providers are integrated |
| 07-component-graph.md | Component dependency graph |
| 08-data-model.md | Entities and relationships |
| 09-state-machine.md | Application lifecycle states |
| 10-request-lifecycle.md | How a request flows through the system |
| 11-error-handling.md | Error taxonomy and pipeline |
| 12-security-model.md | Threat model, trust boundaries, secret rules |
| 13-authentication.md | Auth architecture |
| 14-interface-specification.md | CLI / API / UI surface |
| 15-ux-guidelines.md | Output and UX conventions |
| 16-configuration.md | Config precedence and shape |
| 17-storage.md | Storage abstraction |
| 18-observability.md | Logging, metrics, diagnostics |
| 19-resilience.md | Retry/backoff rules |
| 20-testing-strategy.md | Unit/integration/E2E approach |
| 21-test-pyramid.md | Test distribution |
| 22-quality-gates.md | Definition of done |
| 23-ci-cd.md | Pipeline stages |
| 24-dependency-management.md | Rules for adding dependencies |
| 25-integration-contract.md | Adapter contract for external services |
| 26-rate-limiting.md | Respecting third-party limits |
| 27-performance.md | What to measure, optimization order |
| 28-documentation.md | Required docs |
| 29-roadmap.md | Phased plan |
| 30-task-breakdown.md | Task template + examples |
| 31-decision-log.md | ADRs |
| 32-risk-register.md | Known risks and mitigations |
| 33-change-management.md | Process for big changes |
| 34-backward-compatibility.md | Compatibility process |
| 35-release-engineering.md | Release checklist |
| 36-versioning.md | SemVer rules |
| 37-backup-recovery.md | Data recovery plan |
| 38-failure-scenarios.md | Failure modes to test |
| 39-ai-verification-system.md | Agent self-verification + completion report |
| 40-ai-decision-tree.md | How the agent resolves ambiguity |
| 41-master-system-graph.md | The whole lifecycle in one diagram |
| 42-master-ai-instruction.md | Paste-in instruction for a coding agent |
