"""M30 — Deterministic connector certification fingerprint.

Fingerprint is content-based (hashes of relevant runtime surfaces + manifest).
Documentation-only paths are excluded unless they are the sole source of policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.conformance.models import CONFORMANCE_SPEC_VERSION

ROOT = Path(__file__).resolve().parents[3]

# Runtime-affecting modules — changes invalidate certification
FINGERPRINT_PATHS: tuple[str, ...] = (
    "saathi/connectors/gov/models.py",
    "saathi/connectors/gov/runtime.py",
    "saathi/connectors/gov/gateway_bridge.py",
    "saathi/connectors/gov/policy.py",
    "saathi/connectors/gov/side_effects.py",
    "saathi/connectors/gov/redaction.py",
    "saathi/connectors/gov/auth.py",
    "saathi/connectors/gov/registry.py",
    "saathi/connectors/gov/bypass_guard.py",
    "saathi/connectors/gov/adapters/http.py",
    "saathi/connectors/gov/adapters/mcp.py",
    "saathi/connectors/gov/adapters/browser.py",
    "saathi/connectors/gov/adapters/local_tool.py",
    "saathi/connectors/registry/builtins.py",
    "saathi/connectors/registry/trust.py",
    "saathi/connectors/registry/capabilities.py",
    "saathi/connectors/registry/validation.py",
    "saathi/connectors/registry/deps.py",
    "saathi/connectors/conformance/models.py",
    "saathi/connectors/conformance/specification.py",
    "saathi/connectors/conformance/assessor.py",
    "saathi/connectors/conformance/sandbox.py",
    "saathi/connectors/conformance/eligibility.py",
)

# Docs never participate in fingerprint (false-positive control)
DOC_EXCLUDES_PREFIX = ("docs/",)


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def package_surface_hashes(*, root: Optional[Path] = None) -> dict[str, str]:
    base = root or ROOT
    out: dict[str, str] = {}
    for rel in FINGERPRINT_PATHS:
        out[rel] = _file_sha256(base / rel)
    return out


def manifest_fingerprint_material(manifest: Any) -> dict[str, Any]:
    """Extract identity/runtime ceiling fields from a manifest (no timestamps)."""
    if hasattr(manifest, "to_dict"):
        d = manifest.to_dict()
    elif isinstance(manifest, dict):
        d = dict(manifest)
    else:
        d = {"repr": repr(manifest)}
    # Drop non-behavioral timestamps
    for k in ("created_at", "updated_at", "deprecated_at", "lifecycle_state"):
        d.pop(k, None)
    return d


def compute_certification_fingerprint(
    *,
    connector_id: str,
    manifest: Any = None,
    root: Optional[Path] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """Deterministic SHA-256 fingerprint for connector certification inputs."""
    material = {
        "schema": "m30.certification_fingerprint.v1",
        "spec_version": CONFORMANCE_SPEC_VERSION,
        "connector_id": connector_id,
        "manifest": manifest_fingerprint_material(manifest) if manifest is not None else {},
        "surface": package_surface_hashes(root=root),
        "extra": extra or {},
    }
    digest = hashlib.sha256(_stable_json(material).encode("utf-8")).hexdigest()
    return digest


def fingerprint_report(
    *,
    connector_id: str,
    manifest: Any = None,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    fp = compute_certification_fingerprint(
        connector_id=connector_id, manifest=manifest, root=root,
    )
    return {
        "schema": "m30.fingerprint_report.v1",
        "connector_id": connector_id,
        "fingerprint": fp,
        "spec_version": CONFORMANCE_SPEC_VERSION,
        "surface_paths": list(FINGERPRINT_PATHS),
        "docs_excluded": True,
        "privacy_safe": True,
    }
