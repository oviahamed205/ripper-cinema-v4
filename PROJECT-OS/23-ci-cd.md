# CI/CD PIPELINE

```
Git Push
   │
   ▼
Format Check
   │
   ▼
Lint
   │
   ▼
Type Check
   │
   ▼
Unit Tests
   │
   ▼
Integration Tests
   │
   ▼
Security Scan (secrets + dependency audit)
   │
   ▼
Build
   │
   ▼
E2E Tests
   │
   ▼
Release Candidate
   │
   ▼
Release
```
See `.github/workflows/` for a starter GitHub Actions pipeline implementing this.
