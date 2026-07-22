"""M32 — Deterministic provider verification fingerprint.

Fingerprint material: provider identity, adapter version, connector manifest,
auth profile, operation set, request/response schema surfaces, normalization
rules, retry policy, timeout policy, rate-limit policy, side-effect + data
classification, redaction policy surface, test corpus, and simulator version.

Any material change makes verification STALE. Read-only eligibility checks never
recompute-and-mutate; refresh happens only through explicit verification.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.providers.models import M32_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[3]

# Provider-runtime surfaces whose change must invalidate verification
PROVIDER_FINGERPRINT_PATHS: tuple[str, ...] = (
    "saathi/connectors/providers/models.py",
    "saathi/connectors/providers/contract.py",
    "saathi/connectors/providers/config.py",
    "saathi/connectors/providers/normalization.py",
    "saathi/connectors/providers/errors.py",
    "saathi/connectors/providers/retry.py",
    "saathi/connectors/providers/idempotency.py",
    "saathi/connectors/providers/ratelimit.py",
    "saathi/connectors/providers/registry.py",
    "saathi/connectors/providers/adapters/echo_provider.py",
    "saathi/connectors/testing/provider_simulator.py",
)

DOC_EXCLUDES_PREFIX = ("docs/",)


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def provider_surface_hashes(*, root: Optional[Path] = None) -> dict[str, str]:
    base = root or ROOT
    return {rel: _file_sha256(base / rel) for rel in PROVIDER_FINGERPRINT_PATHS}


def compute_provider_fingerprint(
    *,
    identity: Any,
    config: Any = None,
    connector_manifest: Any = None,
    test_corpus_id: str = "",
    simulator_version: str = "",
    root: Optional[Path] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """Deterministic SHA-256 fingerprint for provider verification inputs."""
    ident = identity.to_dict() if hasattr(identity, "to_dict") else dict(identity or {})
    cfg = config.to_dict() if hasattr(config, "to_dict") else (dict(config) if config else {})
    manifest = {}
    if connector_manifest is not None:
        manifest = connector_manifest.to_dict() if hasattr(connector_manifest, "to_dict") else dict(connector_manifest)
        for k in ("created_at", "updated_at", "deprecated_at", "lifecycle_state"):
            manifest.pop(k, None)

    material = {
        "schema": "m32.provider_fingerprint.v1",
        "spec_version": M32_SCHEMA_VERSION,
        "identity": ident,
        "config": cfg,
        "connector_manifest": manifest,
        "test_corpus_id": test_corpus_id,
        "simulator_version": simulator_version,
        "surface": provider_surface_hashes(root=root),
        "extra": extra or {},
    }
    return hashlib.sha256(_stable_json(material).encode("utf-8")).hexdigest()


def fingerprint_report(
    *,
    identity: Any,
    config: Any = None,
    connector_manifest: Any = None,
    test_corpus_id: str = "",
    simulator_version: str = "",
    root: Optional[Path] = None,
) -> dict[str, Any]:
    fp = compute_provider_fingerprint(
        identity=identity, config=config, connector_manifest=connector_manifest,
        test_corpus_id=test_corpus_id, simulator_version=simulator_version, root=root,
    )
    pid = getattr(identity, "provider_id", "") or (identity or {}).get("provider_id", "")
    return {
        "schema": "m32.provider_fingerprint_report.v1",
        "provider_id": pid,
        "fingerprint": fp,
        "spec_version": M32_SCHEMA_VERSION,
        "surface_paths": list(PROVIDER_FINGERPRINT_PATHS),
        "docs_excluded": True,
        "privacy_safe": True,
    }
