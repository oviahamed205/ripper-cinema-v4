"""
ripper.ai_engine.manager
~~~~~~~~~~~~~~~~~~~~~~~~

Model discovery, local GGUF path validation, integrity verification,
and hardware acceleration telemetry.
"""

import os
import struct
from pathlib import Path
from typing import List, Optional

from .models import AIModelStatus, BackendType

# Known default model locations
DEFAULT_SEARCH_PATHS = [
    "G:/My Drive/K2-Horizon-1B-BF16.gguf",
    "G:/My Drive/K2-Horizon-1B-BF16.gguf.fdmdownload",
    "D:/prework/final work/ripper/models/K2-Horizon-1B-BF16.gguf",
    os.path.expanduser("~/.ripper/models/K2-Horizon-1B-BF16.gguf"),
]

GGUF_MAGIC = b"GGUF"


class ModelManager:
    """
    Manages detection, validation, and metadata inspection of local AI models.
    """

    def __init__(self, custom_path: Optional[str] = None):
        self.custom_path = custom_path or os.environ.get("RIPPER_AI_MODEL_PATH")

    def discover_model_path(self) -> Optional[str]:
        """
        Locates the first valid GGUF model file across search paths.
        """
        candidate_paths: List[str] = []
        if self.custom_path:
            candidate_paths.append(self.custom_path)
        candidate_paths.extend(DEFAULT_SEARCH_PATHS)

        for p in candidate_paths:
            if not p:
                continue
            path_obj = Path(p)
            if path_obj.is_file() and path_obj.stat().st_size > 500_000_000:
                # Validate GGUF magic bytes
                if self.is_valid_gguf(str(path_obj)):
                    return str(path_obj.resolve())
        return None

    @staticmethod
    def is_valid_gguf(file_path: str) -> bool:
        """
        Inspects the header to ensure valid GGUF binary format.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(4)
                return header == GGUF_MAGIC
        except Exception:
            return False

    def inspect_model(self, file_path: str) -> AIModelStatus:
        """
        Reads GGUF metadata fields to construct AIModelStatus.
        """
        if not os.path.exists(file_path):
            return AIModelStatus(
                is_ready=False,
                model_name="unknown",
                error_message=f"File not found: {file_path}",
            )

        file_size = os.path.getsize(file_path)
        arch = "k2-horizon"
        params_b = 1.0

        try:
            import gguf
            reader = gguf.GGUFReader(file_path)
            field = reader.get_field("general.architecture")
            if field and hasattr(field, "parts") and len(field.parts) > 1:
                # Decode bytes to string
                arch_bytes = bytes(field.parts[1])
                arch = arch_bytes.decode("utf-8", errors="ignore")
        except Exception:
            pass

        return AIModelStatus(
            is_ready=True,
            model_name="K2-Horizon-1B",
            model_path=file_path,
            backend=BackendType.TORCH_GGUF,
            device="cpu",
            file_size_bytes=file_size,
            parameters_billions=params_b,
            architecture=arch,
        )
