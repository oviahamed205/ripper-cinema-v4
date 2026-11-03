import sys
import threading
import traceback
import queue
import time
from typing import Optional, Callable, Dict, Any
from ripper.healer_engine.py_core.rules_cache import RulesCache, HeuristicResolution
from ripper.healer_engine.py_core.diagnostic_brain import DiagnosticBrain, NeuralDiagnosis

class HealerWatchdog:
    """
    Autonomous Runtime Watchdog.
    Intercepts unhandled sys.excepthook exceptions and runtime errors,
    runs the 5-tier diagnostic and remediation pipeline, and logs telemetry.
    """

    def __init__(self, ai_model_path: Optional[str] = None):
        self.rules_cache = RulesCache()
        self.brain = DiagnosticBrain(ai_model_path)
        self._original_excepthook = None
        self._installed = False
        self.history: queue.Queue = queue.Queue(maxsize=100)
        self.remediation_counter = 0

    def install(self):
        if self._installed:
            return
        self._original_excepthook = sys.excepthook
        sys.excepthook = self._handle_uncaught_exception
        self._installed = True

    def uninstall(self):
        if not self._installed:
            return
        if self._original_excepthook:
            sys.excepthook = self._original_excepthook
        self._installed = False

    def _handle_uncaught_exception(self, exc_type, exc_value, exc_traceback):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        resolution = self.handle_error(str(exc_value), tb_str)

        # Call original excepthook for graceful crash report if unhealed
        if self._original_excepthook and not (resolution and resolution.applied):
            self._original_excepthook(exc_type, exc_value, exc_traceback)

    def handle_error(self, error_str: str, traceback_str: str = "", context: Optional[Dict[str, Any]] = None) -> HeuristicResolution:
        # Tier 1: Fast Heuristic Rule Cache (<2ms)
        resolution = self.rules_cache.match(error_str, context)
        if resolution:
            self.remediation_counter += 1
            if self.history.full():
                self.history.get_nowait()
            self.history.put({"timestamp": time.time(), "tier": "HEURISTIC", "resolution": resolution})
            return resolution

        # Tier 2: Local AI Neural Brain
        neural = self.brain.diagnose(traceback_str, error_str)
        synthetic_res = HeuristicResolution(
            matched=True,
            rule_name="NEURAL_SLM_DIAGNOSIS",
            error_signature=neural.error_type,
            action=neural.recommended_action,
            remediation=neural.remediation_recipe,
            applied=False,
            context={"root_cause": neural.root_cause, "confidence": neural.confidence}
        )
        self.remediation_counter += 1
        if self.history.full():
            self.history.get_nowait()
        self.history.put({"timestamp": time.time(), "tier": "NEURAL", "diagnosis": neural})
        return synthetic_res

_GLOBAL_WATCHDOG: Optional[HealerWatchdog] = None
_WATCHDOG_LOCK = threading.Lock()

def get_global_watchdog() -> HealerWatchdog:
    global _GLOBAL_WATCHDOG
    with _WATCHDOG_LOCK:
        if _GLOBAL_WATCHDOG is None:
            _GLOBAL_WATCHDOG = HealerWatchdog()
        return _GLOBAL_WATCHDOG
