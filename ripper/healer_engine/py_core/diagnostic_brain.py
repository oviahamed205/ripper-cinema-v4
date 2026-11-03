import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class NeuralDiagnosis:
    error_type: str
    severity: str
    root_cause: str
    recommended_action: str
    confidence: float
    remediation_recipe: str

class DiagnosticBrain:
    """
    Neural Reasoning Engine for novel errors that miss Tier 1 heuristic cache.
    Interfaces with the local K2-Horizon 1B GGUF model via ChatML / structured GBNF prompt.
    """

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or r"G:\My Drive\K2-Horizon-1B-BF16.gguf"
        self._llm_instance = None

    def _get_local_ai_inference(self, prompt: str) -> Optional[str]:
        try:
            from ripper.ai_engine import get_local_ai
            engine = get_local_ai(self.model_path)
            if engine and engine.is_loaded():
                return engine.infer(prompt, max_new_tokens=256)
        except Exception:
            pass
        return None

    def diagnose(self, traceback_str: str, stderr_context: str = "") -> NeuralDiagnosis:
        combined = f"{stderr_context}\n{traceback_str}".strip()

        prompt = (
            "<|im_start|>system\n"
            "You are the Ripper Autonomous Diagnostics Agent. You inspect stack traces and stderr outputs, "
            "determine root causes, and output a strict JSON object with fields: "
            "error_type, severity (CRITICAL/HIGH/MEDIUM/LOW), root_cause, recommended_action (RETRY/PATCH_AST/ENV_FIX/FALLBACK/IGNORE), "
            "confidence (0.0 to 1.0), and remediation_recipe.<|im_end|>\n"
            f"<|im_start|>user\nDiagnose this failure:\n{combined[-1500:]}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        raw_output = self._get_local_ai_inference(prompt)

        if raw_output:
            try:
                # Strip any markdown fences
                cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", raw_output).strip()
                data = json.loads(cleaned)
                return NeuralDiagnosis(
                    error_type=data.get("error_type", "UNKNOWN_ERROR"),
                    severity=data.get("severity", "MEDIUM"),
                    root_cause=data.get("root_cause", "Unspecified issue identified by neural model"),
                    recommended_action=data.get("recommended_action", "RETRY"),
                    confidence=float(data.get("confidence", 0.75)),
                    remediation_recipe=data.get("remediation_recipe", "Apply default fallback handler")
                )
            except Exception:
                pass

        # Offline deterministic fallback diagnostic if LLM is unavailable or output malformed
        error_line = [line for line in traceback_str.splitlines() if line.strip()][-1] if traceback_str else "Unknown Error"
        return NeuralDiagnosis(
            error_type="RUNTIME_ANOMALY",
            severity="MEDIUM",
            root_cause=f"Traceback terminating in: {error_line}",
            recommended_action="FALLBACK",
            confidence=0.85,
            remediation_recipe="Wrap caller in auto_heal defensive decorator and log diagnostic payload."
        )
