"""LONG-DURATION-SHADOW-OBSERVATION-1 — provenance and epoch bookkeeping.

An epoch is a WINDOW OF FROZEN CONFIGURATION over which evidence accumulates.
That is the whole idea, and everything here exists to protect it: evidence
gathered under one strategy version, cost model and monitoring policy cannot be
appended to evidence gathered under another and still mean anything.

THIS IS NOT A NEW EVIDENCE STORE. The evidence already has a durable home — the
shadow session, its events, fills and counterfactuals in `ShadowSessionStore`.
This module records WHICH configuration produced WHICH session, and checkpoints
that point back at it. The manifest is an index and a provenance record; the
session is the truth.

WHAT IT DELIBERATELY CANNOT DO: retune, switch strategies, move a threshold,
change a benchmark, or promote anything. An observer that could adjust the thing
it observes produces no evidence at all — only a record of its own interference.
A DEGRADED verdict during an epoch is recorded and left alone.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

from saathi.platform.tg.attribution_v2 import CALCULATION_VERSION as ATTRIBUTION_VERSION
from saathi.platform.tg.health_collector import COLLECTOR_VERSION
from saathi.platform.tg.health_producers import PRODUCER_VERSION
from saathi.platform.tg.shadow_session import SHADOW_SESSION_SCHEMA_VERSION, ShadowMode
from saathi.platform.tg.strategy_monitor import MONITOR_POLICY_VERSION
from saathi.platform.tg.strategy_observation import ADAPTER_VERSION

OBSERVATION_VERSION = "long-duration-shadow-observation/v1.0.0"

#: Where manifests live. Small JSON documents beside the runtime, never a
#: database of their own — the session store already holds the evidence.
DEFAULT_EPOCH_DIR = Path(".runtime/observation-epochs")


class EpochStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    #: Configuration moved underneath it. The evidence up to that point is still
    #: valid FOR THAT CONFIGURATION; what it may not do is continue.
    INVALIDATED = "INVALIDATED"


class InvalidationReason(str, Enum):
    """Every condition that ends an epoch rather than extending it.

    Named exhaustively because the failure mode is silent: nothing crashes when
    incompatible evidence is stitched together, it just quietly stops meaning
    what the numbers claim.
    """

    STRATEGY_VERSION_CHANGED = "STRATEGY_VERSION_CHANGED"
    MONITOR_POLICY_CHANGED = "MONITOR_POLICY_CHANGED"
    COST_MODEL_CHANGED = "COST_MODEL_CHANGED"
    FILL_MODEL_CHANGED = "FILL_MODEL_CHANGED"
    BENCHMARK_CHANGED = "BENCHMARK_CHANGED"
    EXECUTION_SEMANTICS_CHANGED = "EXECUTION_SEMANTICS_CHANGED"
    DATA_PROVENANCE_CHANGED = "DATA_PROVENANCE_CHANGED"
    PIT_BOUNDARY_CHANGED = "PIT_BOUNDARY_CHANGED"
    RUNTIME_WIRING_CHANGED = "RUNTIME_WIRING_CHANGED"
    CODE_SHA_CHANGED = "CODE_SHA_CHANGED"


class CheckpointKind(str, Enum):
    STARTUP = "STARTUP"
    WINDOW = "WINDOW"
    FAULT = "FAULT"
    RESTART = "RESTART"
    EPOCH_CLOSE = "EPOCH_CLOSE"


@dataclass(frozen=True)
class EpochProvenance:
    """Everything that must not move while the epoch runs.

    Fingerprinted as a whole: comparing one hash is how a restart or a later
    process detects that something underneath it changed, without having to
    remember which fields mattered.
    """

    code_sha: str
    branch: str
    strategy_id: str
    strategy_version: str
    qualification_ref: str | None
    mode: str
    data_source: str
    benchmark_version: str | None
    monitor_policy_version: str = MONITOR_POLICY_VERSION
    attribution_version: str = ATTRIBUTION_VERSION
    observation_adapter_version: str = ADAPTER_VERSION
    producer_version: str = PRODUCER_VERSION
    collector_version: str = COLLECTOR_VERSION
    shadow_schema_version: int = SHADOW_SESSION_SCHEMA_VERSION
    observation_version: str = OBSERVATION_VERSION
    guardian_policy_version: str | None = None
    construction_version: str | None = None
    risk_version: str | None = None
    cost_model_version: str | None = None
    fill_model_version: str | None = None

    def fingerprint(self) -> str:
        blob = json.dumps({k: str(v) for k, v in sorted(asdict(self).items())},
                          sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def differences(self, other: "EpochProvenance") -> tuple:
        a, b = asdict(self), asdict(other)
        return tuple(sorted(k for k in a if a[k] != b.get(k)))


#: Which provenance field, when it moves, invalidates rather than annotates.
INVALIDATING_FIELDS = {
    "code_sha": InvalidationReason.CODE_SHA_CHANGED,
    "strategy_version": InvalidationReason.STRATEGY_VERSION_CHANGED,
    "strategy_id": InvalidationReason.STRATEGY_VERSION_CHANGED,
    "monitor_policy_version": InvalidationReason.MONITOR_POLICY_CHANGED,
    "cost_model_version": InvalidationReason.COST_MODEL_CHANGED,
    "fill_model_version": InvalidationReason.FILL_MODEL_CHANGED,
    "benchmark_version": InvalidationReason.BENCHMARK_CHANGED,
    "attribution_version": InvalidationReason.EXECUTION_SEMANTICS_CHANGED,
    "observation_adapter_version": InvalidationReason.PIT_BOUNDARY_CHANGED,
    "data_source": InvalidationReason.DATA_PROVENANCE_CHANGED,
    "mode": InvalidationReason.EXECUTION_SEMANTICS_CHANGED,
    "producer_version": InvalidationReason.RUNTIME_WIRING_CHANGED,
    "collector_version": InvalidationReason.RUNTIME_WIRING_CHANGED,
}


def invalidation_for(before: EpochProvenance, after: EpochProvenance) -> tuple:
    """Which invalidation reasons a provenance change triggers.

    Empty means the epoch may continue. Anything else means a NEW epoch — the
    old evidence keeps its meaning, it simply stops growing.
    """
    reasons = []
    for field_name in before.differences(after):
        reason = INVALIDATING_FIELDS.get(field_name)
        if reason is not None:
            reasons.append(reason.value)
    return tuple(dict.fromkeys(reasons))


@dataclass
class Checkpoint:
    """A pointer into durable evidence, not a copy of it."""

    kind: str
    at: str
    session_id: str | None = None
    #: Counts are cheap and make a manifest readable on its own. They are a
    #: SUMMARY of the session, never a substitute — the session remains the
    #: only thing anything is recomputed from.
    counts: dict = field(default_factory=dict)
    health: str | None = None
    note: str | None = None


@dataclass
class ObservationEpoch:
    """One frozen-configuration observation window."""

    epoch_id: str
    provenance_fingerprint: str
    provenance: dict
    started_at: str
    status: str = EpochStatus.OPEN.value
    session_id: str | None = None
    expected_duration_seconds: int | None = None
    ended_at: str | None = None
    checkpoints: list = field(default_factory=list)
    invalidation_reasons: tuple = ()
    limitations: tuple = ()
    #: Permanent. An observer that could act on what it sees is not an observer.
    authorizes_execution: bool = False

    def to_public(self) -> dict:
        d = asdict(self)
        d["authorizes_execution"] = False
        return d


class EpochStore:
    """Durable manifests as small atomic JSON documents.

    Atomic write-then-rename, mode 0600, one file per epoch. Deliberately not a
    database: the evidence lives in `ShadowSessionStore`, and a second store
    holding the same facts would eventually disagree with it.
    """

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or DEFAULT_EPOCH_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, epoch_id: str) -> Path:
        # Manifests are named, never path-joined from caller input.
        safe = "".join(c for c in epoch_id if c.isalnum() or c in "-_")
        if not safe or safe != epoch_id:
            raise ValueError(f"unsafe epoch id: {epoch_id!r}")
        return self.root / f"{safe}.json"

    def save(self, epoch: ObservationEpoch) -> Path:
        path = self._path(epoch.epoch_id)
        fd, tmp = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(epoch.to_public(), fh, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            # Rename is atomic: a crash mid-write leaves the previous manifest
            # intact rather than a truncated one.
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return path

    def load(self, epoch_id: str) -> ObservationEpoch | None:
        path = self._path(epoch_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        cps = [Checkpoint(**c) for c in data.pop("checkpoints", [])]
        data["invalidation_reasons"] = tuple(data.get("invalidation_reasons") or ())
        data["limitations"] = tuple(data.get("limitations") or ())
        data.pop("authorizes_execution", None)
        return ObservationEpoch(**data, checkpoints=cps)

    def list_epochs(self) -> tuple:
        return tuple(sorted(p.stem for p in self.root.glob("*.json")))


class ShadowObserver:
    """Runs one observation epoch. READ-ONLY with respect to the strategy.

    It opens a shadow session, records checkpoints against it, and closes the
    epoch. It has no method to change a parameter, a threshold, a benchmark or a
    strategy version, and no code path that promotes anything — the absence is
    the guarantee, and a test asserts it structurally rather than trusting this
    sentence.
    """

    def __init__(self, store: EpochStore, session_store, *, epoch: ObservationEpoch):
        self.store = store
        self.sessions = session_store
        self.epoch = epoch

    @classmethod
    def start(
        cls,
        *,
        store: EpochStore,
        session_store,
        provenance: EpochProvenance,
        started_at: str,
        opening_cash,
        market: str = "CRYPTO",
        feed_ref: str = "replay:frozen",
        policy_versions: dict | None = None,
        expected_duration_seconds: int | None = None,
        limitations: tuple = (),
        epoch_id: str | None = None,
    ) -> "ShadowObserver":
        """Open an epoch and the shadow session that will hold its evidence."""
        eid = epoch_id or f"epoch-{uuid.uuid4().hex[:12]}"
        session_id = session_store.open_session(
            mode=ShadowMode(provenance.mode),
            market=market,
            strategy_version=provenance.strategy_version,
            policy_versions=policy_versions or {
                "monitor": provenance.monitor_policy_version,
                "attribution": provenance.attribution_version,
            },
            feed_ref=feed_ref,
            opening_cash=opening_cash,
            started_at=started_at,
            benchmark=provenance.benchmark_version,
        )
        epoch = ObservationEpoch(
            epoch_id=eid,
            provenance_fingerprint=provenance.fingerprint(),
            provenance=asdict(provenance),
            started_at=started_at,
            session_id=session_id,
            expected_duration_seconds=expected_duration_seconds,
            limitations=tuple(limitations),
        )
        obs = cls(store, session_store, epoch=epoch)
        obs.checkpoint(CheckpointKind.STARTUP, at=started_at,
                       note="epoch opened; configuration frozen")
        return obs

    def checkpoint(self, kind: CheckpointKind, *, at: str, health: str | None = None,
                   note: str | None = None) -> Checkpoint:
        """Record a pointer into the session's evidence.

        Counts are read from the session at this moment so a manifest is legible
        alone, but nothing is recomputed from them — the session stays the only
        thing an analysis reads.
        """
        counts = {}
        sid = self.epoch.session_id
        if sid:
            try:
                events = self.sessions.events(sid)
                fills = self.sessions.fills(sid)
                counts = {
                    "events": len(events),
                    "fills": len(fills),
                    "signals": sum(1 for e in events
                                   if str(e.get("kind", "")).upper() == "SIGNAL"),
                    "counterfactuals": len(self.sessions.counterfactuals(sid)),
                }
            except Exception as exc:
                # A checkpoint that cannot count must still record that it
                # happened; losing the checkpoint would lose the fault.
                counts = {"error": f"{type(exc).__name__}"}
        cp = Checkpoint(kind=kind.value, at=at, session_id=sid, counts=counts,
                        health=health, note=note)
        self.epoch.checkpoints.append(cp)
        self.store.save(self.epoch)
        return cp

    def verify_provenance(self, current: EpochProvenance, *, at: str) -> tuple:
        """Check the world has not moved under the epoch.

        Returns the invalidation reasons. Non-empty INVALIDATES rather than
        adapting: the point of an epoch is that its configuration held, so an
        observer that quietly carried on would destroy the only property that
        makes its evidence worth anything.
        """
        before = EpochProvenance(**self.epoch.provenance)
        reasons = invalidation_for(before, current)
        if reasons:
            self.epoch.status = EpochStatus.INVALIDATED.value
            self.epoch.invalidation_reasons = reasons
            self.epoch.ended_at = at
            self.checkpoint(CheckpointKind.EPOCH_CLOSE, at=at,
                            note=f"invalidated: {', '.join(reasons)}")
        return reasons

    def close(self, *, at: str, note: str | None = None) -> ObservationEpoch:
        if self.epoch.status == EpochStatus.OPEN.value:
            self.epoch.status = EpochStatus.CLOSED.value
        self.epoch.ended_at = at
        self.checkpoint(CheckpointKind.EPOCH_CLOSE, at=at, note=note or "epoch closed")
        return self.epoch


def resume(store: EpochStore, session_store, epoch_id: str) -> ShadowObserver | None:
    """Reattach to an epoch after a restart.

    Continuity, not restart: the manifest and the session both already exist, so
    nothing is re-opened, no counter resets, and no fresh HEALTHY is invented for
    a process that merely came back.
    """
    epoch = store.load(epoch_id)
    if epoch is None:
        return None
    return ShadowObserver(store, session_store, epoch=epoch)
