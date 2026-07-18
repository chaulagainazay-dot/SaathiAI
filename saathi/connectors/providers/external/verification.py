"""M33 — External verification store, deterministic fingerprint, and drift.

External read-only verification is an ADDITIONAL layer on top of M30 connector
certification and M32 provider (simulation) verification — it never replaces them.
The maximum state is ``EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS`` and it
implies nothing about production, writes, accounts, CANARY, or ACTIVE.

Invariant (preserved from M31/M32): eligibility reads NEVER mutate the store.
Only explicit verify / drift(mark_stale) / revoke mutate state.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.providers.external.models import (
    EXTERNAL_VERIFIED_STATES,
    ExternalProviderProfile,
    ExternalVerificationState,
    M33_MAX_VERIFICATION,
    M33_SCHEMA_VERSION,
)
from saathi.connectors.providers.external.schema import SchemaContract
from saathi.connectors.providers.external.tls_policy import TlsPolicy

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STORE_PATH = ROOT / "docs" / "evidence" / "m33" / "external_verification_registry.json"
VERIFY_COMMAND_VERSION = "m33.external_verify.v1"

# External-runtime surfaces whose change must invalidate external verification.
EXTERNAL_FINGERPRINT_PATHS: tuple[str, ...] = (
    "saathi/connectors/providers/external/models.py",
    "saathi/connectors/providers/external/endpoint_policy.py",
    "saathi/connectors/providers/external/dns_ssrf.py",
    "saathi/connectors/providers/external/tls_policy.py",
    "saathi/connectors/providers/external/transport.py",
    "saathi/connectors/providers/external/request_envelope.py",
    "saathi/connectors/providers/external/response_envelope.py",
    "saathi/connectors/providers/external/schema.py",
    "saathi/connectors/providers/external/fixtures.py",
    "saathi/connectors/providers/external/profiles.py",
    "saathi/connectors/providers/external/adapters/github_meta.py",
)


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return "missing"
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def external_surface_hashes(*, root: Optional[Path] = None) -> dict[str, str]:
    base = root or ROOT
    return {rel: _file_sha256(base / rel) for rel in EXTERNAL_FINGERPRINT_PATHS}


def compute_external_fingerprint(
    *,
    profile: ExternalProviderProfile,
    tls_policy: Optional[TlsPolicy] = None,
    schema: Optional[SchemaContract] = None,
    fixture_hash: str = "",
    test_corpus_id: str = "m33.corpus.v1",
    verify_command_version: str = VERIFY_COMMAND_VERSION,
    root: Optional[Path] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """Deterministic SHA-256 over every material external-verification input."""
    material = {
        "schema": "m33.external_fingerprint.v1",
        "spec_version": M33_SCHEMA_VERSION,
        "profile": profile.to_dict(),
        "hostname_allowlist": list(profile.hostname_allowlist),
        "allowed_ports": list(profile.allowed_ports),
        "redirect_limit": profile.redirect_limit,
        "response_limit": profile.response_limit_bytes,
        "deadline": profile.deadline_seconds,
        "tls_policy": (tls_policy or TlsPolicy()).to_dict(),
        "schema": schema.to_dict() if schema else {},
        "operation_set": list(profile.operation_set),
        "auth_profile": profile.auth_profile,
        "side_effect_class": profile.side_effect_class,
        "data_classification": profile.data_classification,
        "adapter_version": profile.adapter_version,
        "expected_schema_version": profile.schema_version,
        "fixture_hash": fixture_hash,
        "test_corpus_id": test_corpus_id,
        "verify_command_version": verify_command_version,
        "surface": external_surface_hashes(root=root),
        "extra": extra or {},
    }
    return hashlib.sha256(_stable_json(material).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass
class ExternalVerificationRecord:
    provider_id: str
    state: str = ExternalVerificationState.UNVERIFIED.value
    fingerprint: str = ""
    verified_at: str = ""
    limitations: list[str] = field(default_factory=list)
    evidence_dir: str = ""
    live_call_count: int = 0
    mode: str = "SHADOW"
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExternalVerificationRecord":
        return cls(
            provider_id=str(d.get("provider_id") or ""),
            state=str(d.get("state") or ExternalVerificationState.UNVERIFIED.value),
            fingerprint=str(d.get("fingerprint") or ""),
            verified_at=str(d.get("verified_at") or ""),
            limitations=list(d.get("limitations") or []),
            evidence_dir=str(d.get("evidence_dir") or ""),
            live_call_count=int(d.get("live_call_count") or 0),
            mode=str(d.get("mode") or "SHADOW"),
            history=list(d.get("history") or []),
        )


@dataclass
class ExternalVerificationDecision:
    allowed: bool
    provider_id: str
    state: str
    reason: str = ""
    fresh: bool = False
    fingerprint: str = ""
    current_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalVerificationStore:
    def __init__(self, path: Optional[Path] = None, *, persist: bool = True, clock: Optional[Any] = None):
        import time as _t

        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self.persist = persist
        self.clock = clock or _t.time
        self._lock = threading.RLock()
        self._records: dict[str, ExternalVerificationRecord] = {}
        if persist and self.path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for pid, raw in (data.get("providers") or {}).items():
                self._records[pid] = ExternalVerificationRecord.from_dict(raw)
        except Exception:
            self._records = {}

    def _save(self) -> None:
        if not self.persist:
            return
        payload = {
            "schema": "m33.external_verification_registry.v1",
            "providers": {k: v.to_dict() for k, v in sorted(self._records.items())},
            "privacy_safe": True,
            "trading_guardian": "UNCHANGED / UNENGAGED",
        }
        _atomic_write(self.path, payload)

    def get(self, provider_id: str) -> ExternalVerificationRecord:
        with self._lock:
            return self._records.get(provider_id) or ExternalVerificationRecord(provider_id=provider_id)

    def list_records(self) -> list[ExternalVerificationRecord]:
        with self._lock:
            return [self._records[k] for k in sorted(self._records)]

    def record_verification(
        self,
        provider_id: str,
        *,
        state: str,
        fingerprint: str,
        limitations: Optional[list[str]] = None,
        evidence_dir: str = "",
        verified_at: str = "",
        live_call_count: int = 0,
        mode: str = "SHADOW",
    ) -> ExternalVerificationRecord:
        # enforce the M33 verification ceiling
        try:
            st = ExternalVerificationState(state)
        except ValueError:
            st = ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED
        if st == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS and \
                M33_MAX_VERIFICATION != ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS:
            st = ExternalVerificationState.SIMULATION_VERIFIED
        with self._lock:
            rec = self._records.get(provider_id) or ExternalVerificationRecord(provider_id=provider_id)
            rec.state = st.value
            rec.fingerprint = fingerprint
            rec.limitations = list(limitations or [])
            rec.evidence_dir = evidence_dir
            rec.verified_at = verified_at
            rec.live_call_count = int(live_call_count)
            rec.mode = mode
            rec.history.append({"event": "verify", "state": st.value, "fp": fingerprint[:16], "ts": float(self.clock())})
            rec.history = rec.history[-50:]
            self._records[provider_id] = rec
            self._save()
            return rec

    def mark_stale(self, provider_id: str, *, reason: str = "fingerprint_drift") -> ExternalVerificationRecord:
        with self._lock:
            rec = self._records.get(provider_id) or ExternalVerificationRecord(provider_id=provider_id)
            if rec.state in {s.value for s in EXTERNAL_VERIFIED_STATES} or \
                    rec.state == ExternalVerificationState.SIMULATION_VERIFIED.value:
                rec.history.append({"event": "stale", "from": rec.state, "reason": reason, "ts": float(self.clock())})
                rec.state = ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value
                self._records[provider_id] = rec
                self._save()
            return rec

    def revoke(self, provider_id: str, *, reason: str) -> ExternalVerificationRecord:
        with self._lock:
            rec = self._records.get(provider_id) or ExternalVerificationRecord(provider_id=provider_id)
            rec.history.append({"event": "revoke", "from": rec.state, "reason": reason[:160], "ts": float(self.clock())})
            rec.state = ExternalVerificationState.REVOKED.value
            self._records[provider_id] = rec
            self._save()
            return rec


def resolve_external_verification(
    provider_id: str,
    *,
    profile: ExternalProviderProfile,
    tls_policy: Optional[TlsPolicy] = None,
    schema: Optional[SchemaContract] = None,
    fixture_hash: str = "",
    store: Optional[ExternalVerificationStore] = None,
) -> ExternalVerificationDecision:
    """NON-mutating external eligibility read. Never refreshes state."""
    st = store or ExternalVerificationStore()
    rec = st.get(provider_id)
    current_fp = compute_external_fingerprint(
        profile=profile, tls_policy=tls_policy, schema=schema, fixture_hash=fixture_hash,
    )
    try:
        state = ExternalVerificationState(rec.state)
    except ValueError:
        state = ExternalVerificationState.UNVERIFIED

    if state in (
        ExternalVerificationState.REVOKED, ExternalVerificationState.EXTERNAL_VERIFICATION_FAILED,
        ExternalVerificationState.EXTERNAL_VERIFICATION_STALE, ExternalVerificationState.UNVERIFIED,
        ExternalVerificationState.SIMULATION_VERIFIED,  # simulation alone is not external-verified
    ):
        allowed = False
        reason = f"external_{state.value.lower()}"
        return ExternalVerificationDecision(allowed, provider_id, state.value, reason=reason,
                                            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp)

    fresh = bool(rec.fingerprint and rec.fingerprint == current_fp and state in EXTERNAL_VERIFIED_STATES)
    if not fresh:
        return ExternalVerificationDecision(
            False, provider_id, ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value,
            reason="external_verification_stale", fresh=False,
            fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    return ExternalVerificationDecision(True, provider_id, state.value, reason="ok", fresh=True,
                                        fingerprint=rec.fingerprint, current_fingerprint=current_fp)


def check_external_drift(
    provider_id: str,
    *,
    profile: ExternalProviderProfile,
    tls_policy: Optional[TlsPolicy] = None,
    schema: Optional[SchemaContract] = None,
    fixture_hash: str = "",
    store: Optional[ExternalVerificationStore] = None,
    mark_stale: bool = True,
) -> dict[str, Any]:
    """Detect external drift; optionally mark stale (explicit mutation path)."""
    st = store or ExternalVerificationStore()
    rec = st.get(provider_id)
    current_fp = compute_external_fingerprint(
        profile=profile, tls_policy=tls_policy, schema=schema, fixture_hash=fixture_hash,
    )
    tracked = {s.value for s in EXTERNAL_VERIFIED_STATES} | {ExternalVerificationState.SIMULATION_VERIFIED.value}
    drifted = bool(rec.fingerprint and rec.fingerprint != current_fp and rec.state in tracked)
    if drifted and mark_stale:
        st.mark_stale(provider_id, reason="fingerprint_mismatch")
    return {
        "schema": "m33.external_drift_report.v1",
        "provider_id": provider_id,
        "drifted": drifted,
        "stored_fingerprint": rec.fingerprint[:16],
        "current_fingerprint": current_fp[:16],
        "prior_state": rec.state,
        "ok": not drifted,
        "privacy_safe": True,
    }
