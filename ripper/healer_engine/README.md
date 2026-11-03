# Autonomous AI Self-Healing CLI Watchdog System

A multi-language, 5-tier self-healing architecture that monitors CLI execution, intercepts runtime failures (stderr, unhandled exceptions, non-zero return codes), performs fast heuristic triage (<2ms), leverages local AI reasoning (K2-Horizon 1B GGUF with GBNF grammar) when heuristics miss, and safely applies AST/config patches with automated rollback.

## Subsystems
- **`schemas/`**: Strict GBNF grammars (`diagnosis.gbnf`) and JSON schemas (`patch_plan.json`).
- **`rust_monitor/`**: High-performance PTY tap, zero-copy lockless ring buffer, and SIMD pattern scanning crate.
- **`py_core/`**: Heuristic rules cache, K2-Horizon diagnostic brain, AST safe patcher, and environment doctor.
- **`ts_daemon/`**: Background supervisor with Windows Named Pipe IPC and real-time telemetry streaming.
- **`shell_shims/`**: Shell hooks for PowerShell (`shim.ps1`) and POSIX Bash/Zsh (`shim.sh`).
