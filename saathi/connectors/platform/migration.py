"""M15.1 legacy migration ledger + direct-call bypass scanner.

MIGRATIONS records every legacy integration and its status. `scan_direct_calls`
statically greps protected modules for prohibited provider-client instantiation
that would bypass the connector platform / ExecutionGateway. Constitution Art. I:
no feature module instantiates an external provider client after migration
except as a bounded, recorded transitional exception.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Legacy integration ledger. status ∈ migrated | shim | blocked | deprecated |
# transitional-exception.
MIGRATIONS: list[dict] = [
    {"old": "server.py /api/v1/connectors/* (legacy accounts/manager)",
     "capability": "send_message / registry / accounts", "connector": "telegram + platform",
     "tool": "telegram.send_message", "status": "shim",
     "note": "legacy read routes kept for old UI; new /api/v1/connectors/* is canonical; "
             "execute path to be delegated to ExecutionEngine"},
    {"old": "connectors/adapters/telegram.py direct Bot API",
     "capability": "send_message", "connector": "telegram", "tool": "telegram.send_message",
     "status": "transitional-exception",
     "note": "real Telegram adapter; wrap under platform adapter before removal"},
    {"old": "studio_os publishing direct calls", "capability": "publish_video",
     "connector": "studio_publish", "tool": "studio_publish.publish_video",
     "status": "blocked", "note": "no publishing creds in env; env-blocked"},
    {"old": "local git/filesystem ad-hoc reads", "capability": "inspect_repository",
     "connector": "local_git/local_fs", "tool": "local_git.inspect_repository",
     "status": "migrated", "note": "now real-local adapters via platform (LIVE)"},
]

# Modules that MUST route through the connector platform (no direct clients).
PROTECTED_MODULES = [
    "saathi/connectors/platform",
]

# Prohibited direct provider-client patterns (instantiation / network egress).
_PROHIBITED = [
    re.compile(r"\bopenai\.(OpenAI|ChatCompletion|Client)\b"),
    re.compile(r"\bAnthropic\("),
    re.compile(r"\bgoogleapiclient\b"),
    re.compile(r"\brequests\.(get|post|put|delete)\("),
    re.compile(r"\bhttpx\.(get|post|Client|AsyncClient)\("),
    re.compile(r"\bsocket\.socket\("),
]

# lines allowed to mention these (adapters that ARE the sanctioned boundary,
# and this scanner file itself defining the patterns).
_ALLOW_FILES = {"adapters.py", "migration.py"}


def scan_direct_calls(root: Path | None = None) -> list[dict]:
    root = root or ROOT
    violations: list[dict] = []
    for base in PROTECTED_MODULES:
        d = root / base
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            if py.name in _ALLOW_FILES:
                continue
            try:
                text = py.read_text()
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                for pat in _PROHIBITED:
                    if pat.search(line):
                        violations.append({"file": str(py.relative_to(root)),
                                           "line": i, "pattern": pat.pattern,
                                           "code": s[:120]})
    return violations


def migration_summary() -> dict:
    by = {}
    for m in MIGRATIONS:
        by[m["status"]] = by.get(m["status"], 0) + 1
    return {"total": len(MIGRATIONS), "by_status": by, "records": MIGRATIONS}
