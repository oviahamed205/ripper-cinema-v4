import ast
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class PatchResult:
    success: bool
    file_path: str
    backup_path: Optional[str]
    checksum_before: str
    checksum_after: Optional[str]
    error_message: Optional[str] = None

class AstPatcher:
    """
    Sandboxed AST Code & Config Patcher.
    Validates Python AST structure before writing to disk, ensuring zero syntax corruption.
    Automatically maintains snapshot backups for immediate rollback.
    """

    @staticmethod
    def _compute_sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def validate_code(self, source_code: str) -> bool:
        try:
            ast.parse(source_code)
            return True
        except SyntaxError:
            return False

    def patch_file_safely(self, target_path: str, new_content: str) -> PatchResult:
        if not os.path.exists(target_path):
            return PatchResult(
                success=False,
                file_path=target_path,
                backup_path=None,
                checksum_before="",
                checksum_after=None,
                error_message=f"Target file {target_path} does not exist"
            )

        if not self.validate_code(new_content):
            return PatchResult(
                success=False,
                file_path=target_path,
                backup_path=None,
                checksum_before="",
                checksum_after=None,
                error_message="Syntax validation failed: invalid Python AST"
            )

        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            original_content = f.read()

        chk_before = self._compute_sha256(original_content)
        chk_after = self._compute_sha256(new_content)

        # Create snapshot backup
        backup_path = f"{target_path}.healer_bak"
        shutil.copy2(target_path, backup_path)

        # Atomic write via temporary file
        dir_name = os.path.dirname(target_path)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tmp:
            tmp.write(new_content)
            tmp_name = tmp.name

        try:
            os.replace(tmp_name, target_path)
            return PatchResult(
                success=True,
                file_path=target_path,
                backup_path=backup_path,
                checksum_before=chk_before,
                checksum_after=chk_after,
                error_message=None
            )
        except Exception as ex:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            return PatchResult(
                success=False,
                file_path=target_path,
                backup_path=backup_path,
                checksum_before=chk_before,
                checksum_after=None,
                error_message=str(ex)
            )

    def rollback(self, target_path: str) -> bool:
        backup_path = f"{target_path}.healer_bak"
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, target_path)
            os.remove(backup_path)
            return True
        return False
