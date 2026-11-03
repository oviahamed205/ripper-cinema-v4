import os
import sys
import re
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

pkg_dir = Path(r"C:\Users\M Y T H O S\.gemini\antigravity\scratch\unshorten-cli\unshorten")

forbidden_keywords = [
    re.compile(r"\bTODO\b", re.I),
    re.compile(r"\bFIXME\b", re.I),
    re.compile(r"\bHACK\b", re.I),
    re.compile(r"\bXXX\b", re.I),
    re.compile(r"\bcoming soon\b", re.I),
    re.compile(r"\bnot implemented\b", re.I),
]

findings = []

for root, dirs, files in os.walk(pkg_dir):
    for f in files:
        if f.endswith(".py"):
            fpath = Path(root) / f
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
            for idx, line in enumerate(lines, 1):
                for pat in forbidden_keywords:
                    if pat.search(line):
                        findings.append((fpath.name, idx, line.strip()))

print(f"Total Keyword Violations Found: {len(findings)}")
for fname, line_no, content in findings:
    print(f"  [{fname}:{line_no}] {content}")
