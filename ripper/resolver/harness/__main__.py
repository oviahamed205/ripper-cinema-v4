"""CLI Entrypoint for ripper.resolver.harness."""
import asyncio
import sys
from .runner import main_cli

if __name__ == "__main__":
    sys.exit(asyncio.run(main_cli()))
