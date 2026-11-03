"""
Compatibility shim for OMEGA-RESOLVER v4.0.
The harness has been organized into ripper.resolver.harness.
You can run this directly or via:
    python -m ripper.resolver.harness [--site <domain>] [--limit <n>]
"""
import asyncio
import sys
from ripper.resolver.harness.runner import main_cli

if __name__ == "__main__":
    sys.exit(asyncio.run(main_cli()))
