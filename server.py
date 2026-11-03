"""
Cloud / Standalone Web Server Entrypoint for Couch Control Hub Cinema.
Allows running 24/7 on Render, Railway, Fly.io, Google Cloud Run, or Docker VPS.
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from ripper.remote_hub import run_standalone_server
except ImportError:
    from unshorten.remote_hub import run_standalone_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_standalone_server(port)
