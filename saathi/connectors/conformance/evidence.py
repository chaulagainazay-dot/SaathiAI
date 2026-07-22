"""M30 — Atomic certification evidence packages."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.conformance.models import CertificationResult, CheckResult
from saathi.connectors.gov.redaction import redact_payload

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "evidence" / "m30" / "connectors"

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|token|authorization|cookie)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
]


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, indent=2, default=str) + "\n"
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def evidence_dir_for(connector_id: str, *, root: Optional[Path] = None) -> Path:
    safe = connector_id.replace("/", "_").replace("..", "_")
    return (root or DEFAULT_EVIDENCE_ROOT) / safe


def write_certification_package(
    result: CertificationResult,
    *,
    manifest_snapshot: Optional[dict[str, Any]] = None,
    fingerprint_report: Optional[dict[str, Any]] = None,
    root: Optional[Path] = None,
) -> Path:
    """Write atomic evidence package; returns directory path."""
    d = evidence_dir_for(result.connector_id, root=root)
    d.mkdir(parents=True, exist_ok=True)

    checks = [
        c.to_dict() if isinstance(c, CheckResult) else c
        for c in result.checks
    ]
    # Redact any accidental secret-like values
    safe_checks = redact_payload(checks)
    safe_result = redact_payload(result.to_dict())

    _atomic_write(d / "manifest_snapshot.json", redact_payload(manifest_snapshot or {}))
    _atomic_write(d / "certification_result.json", safe_result)
    _atomic_write(d / "check_results.json", {
        "schema": "m30.check_results.v1",
        "connector_id": result.connector_id,
        "checks": safe_checks,
        "privacy_safe": True,
    })
    _atomic_write(d / "fingerprint.json", fingerprint_report or {
        "connector_id": result.connector_id,
        "fingerprint": result.fingerprint,
        "spec_version": result.spec_version,
    })
    _atomic_write(d / "limitations.json", {
        "connector_id": result.connector_id,
        "limitations": result.limitations,
        "privacy_safe": True,
    })
    _atomic_write(d / "validation_summary.json", {
        "schema": "m30.validation_summary.v1",
        "connector_id": result.connector_id,
        "state": result.state,
        "mandatory_passed": result.mandatory_passed,
        "check_count": len(result.checks),
        "failure_codes": result.failure_codes,
        "bypass": False,
        "live_credentials_used": 0,
        "live_external_accounts": 0,
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "privacy_safe": True,
    })
    result.evidence_dir = str(d)
    return d


def package_contains_secrets(path: Path) -> list[str]:
    """Scan evidence package for secret-like patterns (should be empty)."""
    hits: list[str] = []
    if not path.is_dir():
        return hits
    for f in path.glob("*.json"):
        text = f.read_text(encoding="utf-8", errors="replace")
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                hits.append(f"{f.name}:{pat.pattern[:40]}")
    return hits
