"""Process-boundary proof (Phase 29) bootstrap: a REAL SaathiOS backend process that owns a
seeded Financial Browser runtime + live page. A second process (the test) reaches it only
over authenticated loopback HTTP — it can never touch the Playwright/Page objects here.

Env: SAATHI_BRIDGE_PORT (required), SAATHI_BRIDGE_URL (seed page url), SAATHI_BRIDGE_PROVIDER.
Writes the seeded runtime_id to stdout as `RUNTIME_ID=<id>` before serving.
"""
from __future__ import annotations

import os
import sys

# no password → genuine loopback callers are trusted (Phase 3 authenticated loopback)
os.environ.pop("SAATHI_PASSWORD_HASH", None)

from saathi.platform.finance.browser_runtime import get_runtime_manager
from saathi.platform.finance.policy import Provider

sys.path.insert(0, os.path.dirname(__file__))
from _bridge_fakes import seed_fake_runtime  # noqa: E402

PROVIDER = Provider[os.environ.get("SAATHI_BRIDGE_PROVIDER", "TMS")]
URL = os.environ.get("SAATHI_BRIDGE_URL", "https://nepsetms.com.np/tms/me/memberclientholding")
ROWS = [{"symbol": "NABIL", "quantity": "100", "available": "100", "wacc": "500",
         "displayed_value": "55400"},
        {"symbol": "HDL", "quantity": "50", "available": "50", "wacc": "1100",
         "displayed_value": "60050"}]

rt = seed_fake_runtime(get_runtime_manager(), PROVIDER, url=URL, rows=ROWS,
                       headers=["Symbol", "Qty", "Available", "WACC", "Value"])
print(f"RUNTIME_ID={rt.runtime_id}", flush=True)

import uvicorn  # noqa: E402
from saathi.server import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(os.environ["SAATHI_BRIDGE_PORT"]),
            log_level="warning")
