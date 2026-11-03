import os
import sys
import filecmp
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

glm_dir = Path(r"C:\Users\M Y T H O S\Desktop\unshorten-cli")
our_dir = Path(r"D:\prework\unshorten-cli")

print(f"=== B2B COMPARISON AUDIT ===")
print(f"GLM Version Directory: {glm_dir}")
print(f"Our V2 Directory:      {our_dir}\n")

# Find all files
glm_files = {p.relative_to(glm_dir): p for p in glm_dir.rglob("*.py") if ".git" not in str(p) and "build" not in str(p)}
our_files = {p.relative_to(our_dir): p for p in our_dir.rglob("*.py") if ".git" not in str(p) and "build" not in str(p)}

all_rel_paths = sorted(set(glm_files.keys()).union(set(our_files.keys())))

only_in_glm = []
only_in_our = []
different = []
identical = []

for rel in all_rel_paths:
    if rel in glm_files and rel not in our_files:
        only_in_glm.append(rel)
    elif rel in our_files and rel not in glm_files:
        only_in_our.append(rel)
    else:
        f_glm = glm_files[rel]
        f_our = our_files[rel]
        if filecmp.cmp(f_glm, f_our, shallow=False):
            identical.append(rel)
        else:
            different.append(rel)

print(f"Total Identical Files: {len(identical)}")
print(f"Files ONLY in GLM:    {len(only_in_glm)}")
for f in only_in_glm:
    print(f"  + {f}")

print(f"\nFiles ONLY in Our V2:  {len(only_in_our)}")
for f in only_in_our:
    print(f"  + {f}")

print(f"\nFiles DIFFERENT in content: {len(different)}")
for f in different:
    print(f"  * {f}")
