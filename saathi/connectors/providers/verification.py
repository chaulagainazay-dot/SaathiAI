"""M32 — Provider verification store, drift, and (non-mutating) eligibility read.

Provider verification is an ADDITIONAL eligibility layer — it never replaces M30
connector certification, M25 production certification, rollout, or approval. The
highest state M32 may claim is SHADOW_VERIFIED_WITH_LIMITATIONS (or
SIMULATION_VERIFIED for pure local simulation).

Invariant (M31 correction preserved): eligibility reads never mutate the
verification or certification stores. Only explicit verify/reassess commands and
explicit drift checks (mark_stale) mutate state.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.providers.fingerprint import compute_provider_fingerprint
from saathi.connectors.providers.models import (
    M32_MAX_VERIFICATION,
    ProviderVerificationState,
    VERIFIED_STATES,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE_PATH = ROOT / "docs" / "evidence" / "m32" / "provider_verification_registry.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


@dataclass
class VerificationRecord:
    provider_id: str
    state: str = ProviderVerificationState.UNVERIFIED.value
    fingerprint: str = ""
    verified_at: str = ""
    limitations: list[str] = field(default_factory=list)
    evidence_dir: str = ""
    lease_id: str = ""
    fixture: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VerificationRecord":
        return cls(
            provider_id=str(d.get("provider_id") or ""),
            state=str(d.get("state") or ProviderVerificationState.UNVERIFIED.value),
            fingerprint=str(d.get("fingerprint") or ""),
            verified_at=str(d.get("verified_at") or ""),
            limitations=list(d.get("limitations") or []),
            evidence_dir=str(d.get("evidence_dir") or ""),
            lease_id=str(d.get("lease_id") or ""),
            fixture=bool(d.get("fixture")),
            history=list(d.get("history") or []),
        )


@dataclass
class VerificationDecision:
    allowed: bool
    provider_id: str
    state: str
    reason: str = ""
    fresh: bool = False
    fingerprint: str = ""
    current_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderVerificationStore:
    def __init__(self, path: Optional[Path] = None, *, persist: bool = True, clock: Optional[Any] = None):
        import time as _t
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self.persist = persist
        self.clock = clock or _t.time
        self._lock = threading.RLock()
        self._records: dict[str, VerificationRecord] = {}
        if persist and self.path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for pid, raw in (data.get("providers") or {}).items():
                self._records[pid] = VerificationRecord.from_dict(raw)
        except Exception:
            self._records = {}

    def _save(self) -> None:
        if not self.persist:
            return
        payload = {
            "schema": "m32.provider_verification_registry.v1",
            "providers": {k: v.to_dict() for k, v in sorted(self._records.items())},
            "privacy_safe": True,
            "trading_guardian": "UNCHANGED / UNENGAGED",
        }
        _atomic_write(self.path, payload)

    def get(self, provider_id: str) -> VerificationRecord:
        with self._lock:
            return self._records.get(provider_id) or VerificationRecord(provider_id=provider_id)

    def list_records(self) -> list[VerificationRecord]:
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
        fixture: bool = False,
    ) -> VerificationRecord:
        # enforce M32 verification ceiling
        try:
            st = ProviderVerificationState(state)
        except ValueError:
            st = ProviderVerificationState.FAILED
        if st == ProviderVerificationState.SHADOW_VERIFIED_WITH_LIMITATIONS and M32_MAX_VERIFICATION != ProviderVerificationState.SHADOW_VERIFIED_WITH_LIMITATIONS:
            st = ProviderVerificationState.SIMULATION_VERIFIED
        with self._lock:
            rec = self._records.get(provider_id) or VerificationRecord(provider_id=provider_id)
            rec.state = st.value
            rec.fingerprint = fingerprint
            rec.limitations = list(limitations or [])
            rec.evidence_dir = evidence_dir
            rec.verified_at = verified_at
            rec.fixture = fixture
            rec.lease_id = ""
            rec.history.append({"event": "verify", "state": st.value, "fp": fingerprint[:16], "ts": float(self.clock())})
            rec.history = rec.history[-50:]
            self._records[provider_id] = rec
            self._save()
            return rec

    def mark_stale(self, provider_id: str, *, reason: str = "fingerprint_drift") -> VerificationRecord:
        with self._lock:
            rec = self._records.get(provider_id) or VerificationRecord(provider_id=provider_id)
            if rec.state in {s.value for s in VERIFIED_STATES}:
                rec.history.append({"event": "stale", "from": rec.state, "reason": reason, "ts": float(self.clock())})
                rec.state = ProviderVerificationState.STALE.value
                self._records[provider_id] = rec
                self._save()
            return rec

    def revoke(self, provider_id: str, *, reason: str) -> VerificationRecord:
        with self._lock:
            rec = self._records.get(provider_id) or VerificationRecord(provider_id=provider_id)
            rec.history.append({"event": "revoke", "from": rec.state, "reason": reason[:160], "ts": float(self.clock())})
            rec.state = ProviderVerificationState.REVOKED.value
            self._records[provider_id] = rec
            self._save()
            return rec


# ── Explicit verification (mutating) ─────────────────────────────────────────
def verify_provider(
    provider_id: str,
    *,
    identity: Any,
    config: Any,
    connector_manifest: Any = None,
    test_corpus_id: str = "m32.corpus.v1",
    simulator_version: str = "",
    store: Optional[ProviderVerificationStore] = None,
    state: str = ProviderVerificationState.SIMULATION_VERIFIED.value,
    limitations: Optional[list[str]] = None,
    evidence_dir: str = "",
) -> VerificationRecord:
    """Explicitly (re)assess a provider and persist verification. Mutating by design."""
    fp = compute_provider_fingerprint(
        identity=identity, config=config, connector_manifest=connector_manifest,
        test_corpus_id=test_corpus_id, simulator_version=simulator_version,
    )
    st = store or ProviderVerificationStore()
    lims = list(limitations or [])
    if state == ProviderVerificationState.SIMULATION_VERIFIED.value and "simulation_only_no_live_provider" not in lims:
        lims.append("simulation_only_no_live_provider")
    return st.record_verification(
        provider_id, state=state, fingerprint=fp, limitations=lims,
        evidence_dir=evidence_dir, verified_at=str(int(st.clock())),
    )


# ── Eligibility read (NON-mutating) ──────────────────────────────────────────
def resolve_provider_verification(
    provider_id: str,
    *,
    identity: Any,
    config: Any,
    connector_manifest: Any = None,
    test_corpus_id: str = "m32.corpus.v1",
    simulator_version: str = "",
    store: Optional[ProviderVerificationStore] = None,
) -> VerificationDecision:
    """Decide whether provider verification permits execution. NEVER mutates state."""
    st = store or ProviderVerificationStore()
    rec = st.get(provider_id)
    current_fp = compute_provider_fingerprint(
        identity=identity, config=config, connector_manifest=connector_manifest,
        test_corpus_id=test_corpus_id, simulator_version=simulator_version,
    )
    try:
        state = ProviderVerificationState(rec.state)
    except ValueError:
        state = ProviderVerificationState.UNVERIFIED

    if state in (ProviderVerificationState.REVOKED, ProviderVerificationState.FAILED,
                 ProviderVerificationState.STALE, ProviderVerificationState.UNVERIFIED):
        return VerificationDecision(
            False, provider_id, state.value, reason=f"provider_{state.value.lower()}",
            fresh=False, fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )

    fresh = bool(rec.fingerprint and rec.fingerprint == current_fp and state in VERIFIED_STATES)
    if not fresh:
        # drift observed but READ must not mutate → report stale-by-fingerprint
        return VerificationDecision(
            False, provider_id, ProviderVerificationState.STALE.value,
            reason="provider_verification_stale", fresh=False,
            fingerprint=rec.fingerprint, current_fingerprint=current_fp,
        )
    return VerificationDecision(
        True, provider_id, state.value, reason="ok", fresh=True,
        fingerprint=rec.fingerprint, current_fingerprint=current_fp,
    )


def check_provider_drift(
    provider_id: str,
    *,
    identity: Any,
    config: Any,
    connector_manifest: Any = None,
    test_corpus_id: str = "m32.corpus.v1",
    simulator_version: str = "",
    store: Optional[ProviderVerificationStore] = None,
    mark_stale: bool = True,
) -> dict[str, Any]:
    """Detect drift; optionally mark stale (explicit mutation path)."""
    st = store or ProviderVerificationStore()
    rec = st.get(provider_id)
    current_fp = compute_provider_fingerprint(
        identity=identity, config=config, connector_manifest=connector_manifest,
        test_corpus_id=test_corpus_id, simulator_version=simulator_version,
    )
    drifted = bool(rec.fingerprint and rec.fingerprint != current_fp and rec.state in {s.value for s in VERIFIED_STATES})
    if drifted and mark_stale:
        st.mark_stale(provider_id, reason="fingerprint_mismatch")
    return {
        "schema": "m32.provider_drift_report.v1",
        "provider_id": provider_id,
        "drifted": drifted,
        "stored_fingerprint": rec.fingerprint[:16],
        "current_fingerprint": current_fp[:16],
        "prior_state": rec.state,
        "ok": not drifted,
        "privacy_safe": True,
    }
