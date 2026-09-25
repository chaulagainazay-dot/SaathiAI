#!/usr/bin/env python3
"""M343 — evidence manifest with checksums for the M336–M343 pack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "private-alpha" / "m336_m343_evidence"
DOCS = ROOT / "docs" / "private-alpha"
TRADING = ROOT / "docs" / "trading" / "m336_m343_evidence"


def entry(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    files: list[dict] = []
    for directory in (TRADING, PACK, PACK / "browser"):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name != "EVIDENCE_MANIFEST.json":
                files.append(entry(path))
    for name in (
        "PRIVATE_ALPHA_SCOPE.md",
        "PRIVATE_ALPHA_RELEASE_RUNBOOK.md",
        "PRIVATE_ALPHA_ROLLBACK_RUNBOOK.md",
        "PRIVATE_ALPHA_INCIDENT_RUNBOOK.md",
        "PRIVATE_ALPHA_TESTER_GUIDE.md",
        "PRIVATE_ALPHA_LAUNCH_CHECKLIST.md",
        "M336_M343_PRIVATE_ALPHA_LAUNCH_READINESS.md",
    ):
        path = DOCS / name
        if path.is_file():
            files.append(entry(path))

    manifest = {
        "schema": "m336_m343.evidence_manifest.v1",
        "milestone": "M336-M343",
        "verdict": "PRIVATE_ALPHA_LAUNCH_READINESS_CERTIFIED_WITH_LIMITATIONS",
        "max_state": "PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY",
        "owner_review_status": "OWNER_REVIEW_REQUIRED",
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
        "raw_evidence_preserved": True,
        "note": "Checksums are over the files as committed. Test logs are raw output, "
                "not summaries.",
    }
    out = PACK / "EVIDENCE_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(files), "bytes": manifest["total_bytes"],
                      "manifest": str(out.relative_to(ROOT))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
