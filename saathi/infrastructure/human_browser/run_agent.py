"""Runnable Mac Agent — run THIS on your trusted Mac (never on the VM).

    export SAATHI_BASE_URL=https://140-245-193-190.nip.io
    export SAATHI_TOKEN=...              # same token as the VM (auth to poll)
    export HUMAN_BROWSER_SECRET=...      # shared signing secret (VM signs, this verifies)
    python -m saathi.infrastructure.human_browser.run_agent

It long-polls the VM for signed jobs, verifies each, and drives your real,
already-logged-in Chrome profiles. Requires Playwright + Chrome installed here.
"""
from __future__ import annotations

import os
import sys

from .queue import HttpQueueClient
from .agent import MacAgent
from .chrome_backend import ChromeBackend
from .profiles import ProfileStore


def main() -> int:
    base = os.getenv("SAATHI_BASE_URL", "")
    token = os.getenv("SAATHI_TOKEN", "")
    secret = os.getenv("HUMAN_BROWSER_SECRET", "")
    if not (base and token and secret):
        print("set SAATHI_BASE_URL, SAATHI_TOKEN and HUMAN_BROWSER_SECRET first", file=sys.stderr)
        return 2
    backend = ChromeBackend(ProfileStore())
    if not backend.available():
        print("Playwright not installed here — run: pip install playwright && playwright install chrome",
              file=sys.stderr)
        return 3
    agent = MacAgent(HttpQueueClient(base, token), backend, secret=secret)
    print(f"Mac Agent polling {base} for signed jobs… (Ctrl+C to stop)")
    agent.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
