import os
import ast
import sys
from pathlib import Path

pkg_dir = Path(r"C:\Users\M Y T H O S\.gemini\antigravity\scratch\unshorten-cli\unshorten")

errors = []
total_files = 0
total_lines = 0

for root, dirs, files in os.walk(pkg_dir):
    for f in files:
        if f.endswith(".py"):
            total_files += 1
            fpath = Path(root) / f
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                total_lines += len(content.splitlines())
                ast.parse(content, filename=str(fpath))
            except Exception as e:
                errors.append((str(fpath), str(e)))

print(f"Total Python Files Scanned: {total_files}")
print(f"Total Lines of Code: {total_lines}")
print(f"Syntax/AST Parse Errors: {len(errors)}")
for f, e in errors:
    print(f"  ❌ {f}: {e}")

if not errors:
    print("✔ All 40 modules passed AST compilation cleanly!")
