"""M29 — Deterministic connector manifest validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.connectors.registry.capabilities import (
    ConnectorCapability,
    normalize_capability_classes,
    parse_capability,
)
from saathi.connectors.registry.trust import (
    TrustLevel,
    enforce_capabilities_for_trust,
    parse_trust_level,
    rollout_eligible_for_trust,
)

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

_VALID_ROLLOUT = frozenset({"OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING"})
_VALID_SIDE_EFFECTS = frozenset({
    "READ_ONLY", "LOCAL_MUTATION", "EXTERNAL_MUTATION", "COMMUNICATION",
    "ACCOUNT_CHANGE", "FINANCIAL", "PRIVILEGED", "PROHIBITED",
})
_VALID_EVIDENCE = frozenset({"redacted", "metadata_only", "none_forbidden"})
_VALID_AUTH = frozenset({"none", "env_var", "local_secure", "future_secret_manager"})
_VALID_ENVIRONMENTS = frozenset({"dev", "test", "staging", "production", "local"})


class ManifestValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__(";".join(self.errors) if self.errors else "manifest_invalid")


@dataclass
class ManifestValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ManifestValidationError(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "normalized": dict(self.normalized),
        }


def _as_tuple(val: Any) -> tuple:
    if val is None:
        return ()
    if isinstance(val, (list, tuple, set, frozenset)):
        return tuple(val)
    return (val,)


def _manifest_get(manifest: Any, key: str, default: Any = None) -> Any:
    if isinstance(manifest, dict):
        return manifest.get(key, default)
    return getattr(manifest, key, default)


def validate_manifest(
    manifest: Any,
    *,
    strict: bool = True,
    known_dependency_ids: Optional[set[str]] = None,
) -> ManifestValidationResult:
    """Validate a ConnectorManifest or dict. Deterministic error list."""
    errors: list[str] = []
    warnings: list[str] = []

    cid = str(_manifest_get(manifest, "connector_id") or "").strip()
    if not cid:
        errors.append("missing_connector_id")
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9_.-]*$", cid):
        errors.append("invalid_connector_id_format")

    version = str(_manifest_get(manifest, "version") or "").strip()
    if not version:
        errors.append("missing_version")
    elif not _SEMVER_RE.match(version) and version not in ("1", "1.0"):
        # Accept legacy short versions as warnings for M27 manifests
        if re.match(r"^\d+(\.\d+)*$", version):
            warnings.append(f"non_semver_version:{version}")
        else:
            errors.append(f"invalid_version:{version}")

    # Trust
    trust_raw = _manifest_get(manifest, "trust_level", "INTERNAL")
    try:
        trust = parse_trust_level(trust_raw)
    except ValueError:
        errors.append(f"invalid_trust:{trust_raw}")
        trust = TrustLevel.INTERNAL

    if trust is TrustLevel.PROHIBITED:
        errors.append("trust_prohibited")

    trading = bool(_manifest_get(manifest, "trading", False))
    if trading:
        errors.append("trading_connectors_forbidden")

    # Kind / adapter_type
    kind = _manifest_get(manifest, "kind", None)
    adapter_type = _manifest_get(manifest, "adapter_type", None) or (
        kind.value if hasattr(kind, "value") else kind
    ) or "http"
    adapter_type = str(adapter_type)

    # Capability classes (M29 explicit)
    cap_raw = _manifest_get(manifest, "capability_classes", None)
    if cap_raw is None or (isinstance(cap_raw, (list, tuple)) and len(cap_raw) == 0):
        # Derive defaults from kind — not "missing" for M27 compat
        caps = normalize_capability_classes(None, kind=adapter_type)
        if strict and not _manifest_get(manifest, "capabilities", None):
            # still require some capability signal
            pass
    else:
        try:
            caps = normalize_capability_classes(cap_raw, kind=adapter_type)
        except ValueError as e:
            errors.append(f"invalid_capability:{e}")
            caps = ()

    for c in caps:
        try:
            parse_capability(c)
        except ValueError:
            errors.append(f"invalid_capability:{c}")

    if not caps:
        errors.append("missing_capability")

    violations = enforce_capabilities_for_trust(trust, caps)
    for v in violations:
        errors.append(f"capability_exceeds_trust:{v}")

    # Supported operations
    ops = _as_tuple(
        _manifest_get(manifest, "supported_operations", None)
        or _manifest_get(manifest, "capabilities", None)
    )
    ops = tuple(str(o) for o in ops if str(o).strip())
    if not ops:
        errors.append("missing_supported_operations")
    else:
        seen_ops: set[str] = set()
        for o in ops:
            ol = o.lower()
            if ol in seen_ops:
                errors.append(f"duplicate_operation:{o}")
            seen_ops.add(ol)

    # Rollout compatibility
    rollout = _as_tuple(
        _manifest_get(manifest, "rollout_compatible", None)
        or ("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING")
    )
    rollout = tuple(str(r).upper() for r in rollout)
    for r in rollout:
        if r not in _VALID_ROLLOUT:
            errors.append(f"invalid_rollout:{r}")
    eligible = rollout_eligible_for_trust(trust)
    for r in rollout:
        if r in _VALID_ROLLOUT and r not in eligible:
            errors.append(f"rollout_not_eligible_for_trust:{r}")

    # Side-effect classes
    se = _as_tuple(_manifest_get(manifest, "side_effect_classes", None))
    if not se:
        if strict:
            warnings.append("undeclared_side_effect_classes")
    else:
        for s in se:
            if str(s).upper() not in _VALID_SIDE_EFFECTS:
                errors.append(f"invalid_side_effect:{s}")

    # Auth
    auth_mode = _manifest_get(manifest, "auth_mode", "none")
    auth_s = auth_mode.value if hasattr(auth_mode, "value") else str(auth_mode or "none")
    auth_s = auth_s.lower()
    if auth_s not in _VALID_AUTH:
        errors.append(f"undeclared_auth:{auth_s}")
    auth_env = _as_tuple(_manifest_get(manifest, "auth_env_names", ()))
    secret_refs = _as_tuple(_manifest_get(manifest, "secret_references", ()))
    if auth_s in ("env_var",) and not auth_env and not secret_refs:
        errors.append("undeclared_auth_references")

    # Evidence
    evidence = str(_manifest_get(manifest, "evidence_policy", "") or "").strip()
    if not evidence:
        errors.append("undeclared_evidence")
    elif evidence not in _VALID_EVIDENCE:
        # allow legacy values as warning
        if evidence in ("full", "debug"):
            errors.append(f"invalid_evidence_policy:{evidence}")
        else:
            errors.append(f"undeclared_evidence:{evidence}")

    # Incidents
    incident_policy = _manifest_get(manifest, "incident_policy", None)
    if incident_policy is None or incident_policy == "":
        errors.append("undeclared_incidents")
    elif isinstance(incident_policy, dict):
        if not incident_policy.get("enabled", True) and strict:
            warnings.append("incidents_disabled")
    # string form accepted: "default" | "m26" | "none"
    elif isinstance(incident_policy, str):
        if incident_policy.lower() in ("none", "disabled"):
            errors.append("undeclared_incidents")

    # Health / readiness policies
    health = _manifest_get(manifest, "health_policy", None)
    readiness = _manifest_get(manifest, "readiness_policy", None)
    if not health:
        warnings.append("missing_health_policy")
    if not readiness:
        warnings.append("missing_readiness_policy")

    # Environments
    envs = _as_tuple(_manifest_get(manifest, "supported_environments", ("local", "dev", "test")))
    for e in envs:
        if str(e).lower() not in _VALID_ENVIRONMENTS:
            errors.append(f"invalid_environment:{e}")

    # Dependencies format
    deps = _as_tuple(_manifest_get(manifest, "dependencies", ()))
    deps = tuple(str(d) for d in deps if str(d).strip())
    if known_dependency_ids is not None:
        for d in deps:
            if d not in known_dependency_ids and d != cid:
                errors.append(f"unknown_dependency:{d}")

    # Deprecation metadata consistency
    deprecated = bool(_manifest_get(manifest, "deprecated", False))
    replacement = str(_manifest_get(manifest, "replacement_connector", "") or "")
    if deprecated and not replacement:
        warnings.append("deprecated_without_replacement")
    if replacement and replacement == cid:
        errors.append("replacement_self_reference")

    # Display / owner soft requirements
    display = str(_manifest_get(manifest, "display_name", "") or "")
    owner = str(_manifest_get(manifest, "owner", "") or "")
    if not display:
        warnings.append("missing_display_name")
    if not owner:
        warnings.append("missing_owner")

    normalized = {
        "connector_id": cid,
        "version": version,
        "trust_level": trust.value,
        "adapter_type": adapter_type,
        "capability_classes": [c.value for c in caps],
        "supported_operations": list(ops),
        "rollout_compatible": list(rollout),
        "dependencies": list(deps),
        "deprecated": deprecated,
        "replacement_connector": replacement,
        "auth_mode": auth_s,
        "evidence_policy": evidence or "redacted",
    }

    return ManifestValidationResult(
        ok=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        normalized=normalized,
    )
