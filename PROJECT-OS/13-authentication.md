# AUTHENTICATION

Authentication logic should be isolated behind a single manager/module.

```
Interface Layer
 │
 ▼
Auth Manager
 │
 ├── Login
 ├── Logout
 ├── Status / whoami
 ├── Expiration / refresh
 └── Credential Provider
```

Credential Provider may use:
- OS-native secure credential storage (Keychain / Credential Manager / Secret Service)
- Supported environment variables
- The provider/service's officially supported auth flow (OAuth, API key, etc.)

Never hardcode credentials. Never commit `.env` files with real secrets.

Example commands (adapt to project type):
```
<tool> auth login
<tool> auth status
<tool> auth logout
```
