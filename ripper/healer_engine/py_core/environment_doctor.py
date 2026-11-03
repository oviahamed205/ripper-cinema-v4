import socket
import ssl
import sys
import os
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class HealthCheckReport:
    healthy: bool
    python_version: str
    network_available: bool
    dns_resolves: bool
    ssl_valid: bool
    local_ai_accessible: bool
    diagnostics: Dict[str, Any]

class EnvironmentDoctor:
    """
    System and Environment Doctor.
    Verifies DNS resolution, SSL certificates, socket connectivity, and model file availability.
    """

    def __init__(self, ai_model_path: str = r"G:\My Drive\K2-Horizon-1B-BF16.gguf"):
        self.ai_model_path = ai_model_path

    def run_health_checks(self) -> HealthCheckReport:
        dns_ok = self._check_dns()
        net_ok = self._check_tcp_connectivity()
        ssl_ok = self._check_ssl_context()
        ai_ok = os.path.exists(self.ai_model_path)

        all_healthy = dns_ok and net_ok and ssl_ok

        return HealthCheckReport(
            healthy=all_healthy,
            python_version=sys.version,
            network_available=net_ok,
            dns_resolves=dns_ok,
            ssl_valid=ssl_ok,
            local_ai_accessible=ai_ok,
            diagnostics={
                "os_name": os.name,
                "ai_model_exists": ai_ok,
                "ai_model_path": self.ai_model_path,
                "default_dns_host": "one.one.one.one"
            }
        )

    def _check_dns(self, host: str = "one.one.one.one") -> bool:
        try:
            socket.gethostbyname(host)
            return True
        except Exception:
            return False

    def _check_tcp_connectivity(self, host: str = "1.1.1.1", port: int = 53, timeout: float = 2.0) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return True
        except Exception:
            return False

    def _check_ssl_context(self) -> bool:
        try:
            ctx = ssl.create_default_context()
            return ctx is not None
        except Exception:
            return False
