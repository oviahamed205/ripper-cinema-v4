# CONFIGURATION

## Precedence (highest to lowest)
```
CLI arguments / runtime flags
      ↓
Environment variables
      ↓
Project-local configuration file
      ↓
User/global configuration file
      ↓
Built-in defaults
```

## Example config shape
```
provider = "..."
mode = "..."
output = "stream"
theme = "auto"
```

Never store plaintext secrets in an ordinary, committed configuration file. Use environment variables or a secure secret store, and provide a `.env.example` with no real values.
