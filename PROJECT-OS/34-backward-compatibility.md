# BACKWARD COMPATIBILITY

For any public command / API / interface:
```
Existing behavior → Change proposed → Compatibility analysis → Migration plan → Implementation → Regression test
```
Avoid breaking existing public behavior unnecessarily. If a breaking change is required:
- Document it in the changelog.
- Provide migration instructions.
- Bump the major version.
