"""
Ripper Autonomous Healer Engine.
Multi-language self-healing architecture combining Rust PTY interception,
fast heuristic rule caches, K2-Horizon local neural diagnostics,
sandboxed AST patching, and persistent background IPC.
"""
from ripper.healer_engine.py_core.watchdog import HealerWatchdog, get_global_watchdog
from ripper.healer_engine.py_core.rules_cache import RulesCache, HeuristicResolution
from ripper.healer_engine.py_core.diagnostic_brain import DiagnosticBrain, NeuralDiagnosis
from ripper.healer_engine.py_core.ast_patcher import AstPatcher, PatchResult
from ripper.healer_engine.py_core.environment_doctor import EnvironmentDoctor, HealthCheckReport

__all__ = [
    "HealerWatchdog",
    "get_global_watchdog",
    "RulesCache",
    "HeuristicResolution",
    "DiagnosticBrain",
    "NeuralDiagnosis",
    "AstPatcher",
    "PatchResult",
    "EnvironmentDoctor",
    "HealthCheckReport",
]
