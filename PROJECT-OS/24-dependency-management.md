# DEPENDENCY MANAGEMENT

Before adding any dependency:
1. Can the standard library solve this instead?
2. Is it actively maintained?
3. What license does it use — compatible with this project?
4. Any known security history / CVEs?
5. What's the install/bundle size cost?
6. Is it compatible with target platforms?
7. Document *why* it's needed (in the PR description or decision log).

Avoid duplicate dependencies that solve the same problem. Update dependencies regularly and re-test after updates.
