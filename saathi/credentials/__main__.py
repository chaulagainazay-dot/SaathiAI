"""Entry point: python -m saathi.credentials <command>."""
from __future__ import annotations

import sys

from saathi.credentials.cli import main

if __name__ == "__main__":
    sys.exit(main())
