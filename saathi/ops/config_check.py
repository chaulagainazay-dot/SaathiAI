"""M13.5 configuration validation — never prints secret values.

Reports each config item as valid / warning / blocking, with secrets shown
only as PRESENT/ABSENT.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# (env key, required?, is_secret?)
_ENV = [
    ("SAATHI_TOKEN", False, True),
    ("ANTHROPIC_API_KEY", False, True),
    ("GROQ_API_KEY", False, True),
    ("GOOGLE_API_KEY", False, True),
    ("HF_TOKEN", False, True),
    ("PORT", False, False),
    ("SAATHI_HOST", False, False),
    ("LLM_PROVIDER", False, False),
]


def check_config() -> dict:
    items = []
    blocking = 0
    warnings = 0

    for key, required, secret in _ENV:
        present = bool(os.getenv(key))
        if required and not present:
            status = "blocking"; blocking += 1
        elif secret and not present:
            status = "warning"; warnings += 1  # optional provider key absent
        else:
            status = "valid"
        items.append({"key": key, "status": status,
                     "value": ("PRESENT" if present else "ABSENT") if secret
                     else (os.getenv(key) if present else "unset")})

    # paths / flags
    data_dir = ROOT / "data"
    items.append({"key": "data_dir_writable", "status": "valid" if os.access(
        str(data_dir if data_dir.exists() else ROOT), os.W_OK) else "blocking",
        "value": str(data_dir)})
    debug = os.getenv("SAATHI_DEBUG", "0") == "1"
    if debug:
        warnings += 1
    items.append({"key": "debug_mode", "status": "warning" if debug else "valid",
                 "value": "on" if debug else "off"})

    # secret-in-repo guard (firebase-admin.json must stay untracked)
    fb = ROOT / "firebase-admin.json"
    import subprocess
    tracked = ""
    try:
        tracked = subprocess.run(["git", "ls-files", "firebase-admin.json"],
                                 cwd=str(ROOT), capture_output=True, text=True,
                                 timeout=3).stdout.strip()
    except Exception:
        pass
    if tracked:
        blocking += 1
    items.append({"key": "firebase_key_untracked",
                 "status": "blocking" if tracked else "valid",
                 "value": "TRACKED (leak!)" if tracked else "untracked"})

    return {"ok": blocking == 0, "blocking": blocking, "warnings": warnings,
            "items": items}
