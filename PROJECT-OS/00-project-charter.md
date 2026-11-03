# PROJECT CHARTER

Project Name: unshorten-cli
Project Type: CLI
Version: 1.0.0
Status: Production / Stable
Primary Development Environment: Antigravity IDE
Primary Coding Agent: Antigravity (Gemini 3.5 Flash)
Architecture Style: Modular / Resolver-Based / Testable / Secure / Observable

## Development Philosophy

```
Specification
    ↓
Requirements
    ↓
Architecture
    ↓
Technical Design
    ↓
Implementation
    ↓
Testing
    ↓
Security Review
    ↓
Verification
    ↓
Documentation
    ↓
Release
    ↓
Monitoring
    ↓
Iteration
```

## 1. Problem
Traces shortened and wrapped URLs safely without risking ad popups, client-side browser trackers, or phishing redirects in a standard browser.

## 2. Target Users
- Power users, security researchers, and developers who want to expand short/wrapped links.
- Users seeking to play media from redirecting ad-heavy portals directly in native desktop players.

## 3. Product
A Python command-line utility (`unshorten`) and an interactive cyberpunk CLI dashboard featuring high-speed parallel unshortening, threat analysis, media grid parsing, and PotPlayer stream streaming.

## 4. Vision
An extensible universal unshortener that serves as a firewall between shorten/ad-links and the user, expanding arbitrary layouts automatically.

## 5. Goals
- Trace HTTP redirect codes (`301`, `302`, etc.) recursive logic.
- Circumvent meta-refresh tags and client-side JavaScript redirects.
- Support deep search endpoints and local streaming playback integration.
- Fast parallel batch mode with export formats.

## 6. Non-Goals
The project will NOT:
- Function as a web browser.
- Host download mirrors or contents locally.
