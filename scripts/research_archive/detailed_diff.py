import difflib
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

glm_dir = Path(r"C:\Users\M Y T H O S\Desktop\unshorten-cli")
our_dir = Path(r"D:\prework\unshorten-cli")

diff_files = [
    "unshorten/anystream.py",
    "unshorten/proxy_engine.py",
    "unshorten/resolver.py",
    "unshorten/downloader.py",
    "unshorten/player.py",
    "unshorten/stream_buffer.py",
    "unshorten/remote_hub.py",
    "unshorten/hunter/site_hunter.py",
    "unshorten/cli.py",
]

for rel in diff_files:
    f_glm = glm_dir / rel
    f_our = our_dir / rel
    print(f"\n{'='*70}")
    print(f"DIFF FOR: {rel}")
    print(f"{'='*70}")
    if not f_glm.exists():
        print("  [Missing in GLM]")
        continue
    if not f_our.exists():
        print("  [Missing in Our V2]")
        continue
    
    t_glm = f_glm.read_text(encoding="utf-8", errors="replace").splitlines()
    t_our = f_our.read_text(encoding="utf-8", errors="replace").splitlines()
    
    diff = list(difflib.unified_diff(t_our, t_glm, fromfile="Our_V2", tofile="GLM_Desktop", lineterm=""))
    print(f"Total diff lines: {len(diff)}")
    for line in diff[:40]: # show first 40 lines
        print(line)
    if len(diff) > 40:
        print(f"... and {len(diff) - 40} more lines of diff ...")
