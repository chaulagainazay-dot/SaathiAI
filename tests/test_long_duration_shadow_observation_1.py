"""LONG-DURATION-SHADOW-OBSERVATION-1 — evidence under frozen configuration.

An epoch is only worth something if its configuration held for the whole of it.
So most of these tests are about the ways that could silently stop being true:
provenance drifting, evidence from two configurations being stitched together,
a restart resetting counters, or the observer quietly "fixing" what it observes.
"""
from __future__ import annotations

import ast
import json
from decimal import Decimal
from pathlib import Path

import pytest

from saathi.platform.research.store import ResearchStore
from saathi.platform.tg.observation_epoch import (
    OBSERVATION_VERSION,
    CheckpointKind,
    EpochProvenance,
    EpochStatus,
    EpochStore,
    InvalidationReason,
    ObservationEpoch,
    ShadowObserver,
    invalidation_for,
    resume,
)
from saathi.platform.tg.shadow_session import (
    ShadowEventKind,
    ShadowMode,
    ShadowSessionStore,
)

SRC = Path("saathi/platform/tg/observation_epoch.py")
T0 = "2026-09-06T00:00:00Z"
T1 = "2026-09-07T00:00:00Z"


def _prov(**over):
    p = dict(
        code_sha="78921d75f058ee589f1e8c69626ace843e32010a",
        branch="observation/epoch-1",
        strategy_id="btc-mean-reversion",
        strategy_version="btc-mean-reversion@frozen-1",
        qualification_ref="qual-sha-abc123",
        mode=ShadowMode.REPLAY.value,
        data_source="replay:btc-2026-08",
        benchmark_version="BTC_BUY_AND_HOLD",
        cost_model_version="cost/v1",
        fill_model_version="fill/v1",
    )
    p.update(over)
    return EpochProvenance(**p)


@pytest.fixture()
def stores(tmp_path):
    return (EpochStore(tmp_path / "epochs"),
            ShadowSessionStore(research_store=ResearchStore(db_path=tmp_path / "s.sqlite3")))


def _start(stores, **over):
    store, sessions = stores
    params = dict(store=store, session_store=sessions, provenance=_prov(),
                  started_at=T0, opening_cash="250000",
                  expected_duration_seconds=7 * 24 * 3600,
                  limitations=("no real orders", "no private account"))
    params.update(over)
    return ShadowObserver.start(**params)


# ══ provenance is captured, not assumed ═════════════════════════════════════
def test_an_epoch_records_every_layer_version_at_start(stores):
    obs = _start(stores)
    p = obs.epoch.provenance
    for key in ("code_sha", "strategy_version", "qualification_ref", "mode",
                "data_source", "benchmark_version", "monitor_policy_version",
                "attribution_version", "observation_adapter_version",
                "producer_version", "collector_version", "shadow_schema_version",
                "cost_model_version", "fill_model_version"):
        assert p.get(key) not in (None, ""), key
    assert p["observation_version"] == OBSERVATION_VERSION


def test_the_provenance_fingerprint_changes_when_any_field_moves(stores):
    base = _prov()
    assert base.fingerprint() == _prov().fingerprint()
    assert base.fingerprint() != _prov(strategy_version="other").fingerprint()
    assert base.fingerprint() != _prov(cost_model_version="cost/v2").fingerprint()


def test_the_epoch_opens_a_real_shadow_session_rather_than_a_private_log(stores):
    """The evidence must live where every certified reader already looks."""
    _, sessions = stores
    obs = _start(stores)
    session = sessions.get_session(obs.epoch.session_id)
    assert session is not None
    assert session["mode"] == ShadowMode.REPLAY.value
    assert session["strategy_version"] == "btc-mean-reversion@frozen-1"


# ══ epoch invalidation ══════════════════════════════════════════════════════
@pytest.mark.parametrize("field,value,reason", [
    ("code_sha", "deadbeef", InvalidationReason.CODE_SHA_CHANGED),
    ("strategy_version", "frozen-2", InvalidationReason.STRATEGY_VERSION_CHANGED),
    ("monitor_policy_version", "v2", InvalidationReason.MONITOR_POLICY_CHANGED),
    ("cost_model_version", "cost/v2", InvalidationReason.COST_MODEL_CHANGED),
    ("fill_model_version", "fill/v2", InvalidationReason.FILL_MODEL_CHANGED),
    ("benchmark_version", "ETH_HOLD", InvalidationReason.BENCHMARK_CHANGED),
    ("data_source", "replay:other", InvalidationReason.DATA_PROVENANCE_CHANGED),
    ("attribution_version", "attribution/v3", InvalidationReason.EXECUTION_SEMANTICS_CHANGED),
    ("observation_adapter_version", "adapter/v2", InvalidationReason.PIT_BOUNDARY_CHANGED),
    ("collector_version", "collector/v2", InvalidationReason.RUNTIME_WIRING_CHANGED),
])
def test_a_material_configuration_change_invalidates_rather_than_extends(
        stores, field, value, reason):
    """NO_CROSS_EPOCH_EVIDENCE_MERGE — the silent failure this prevents.

    Nothing crashes when evidence from two configurations is appended together;
    the numbers simply stop meaning what they claim. So the epoch ends.
    """
    obs = _start(stores)
    reasons = obs.verify_provenance(_prov(**{field: value}), at=T1)
    assert reason.value in reasons
    assert obs.epoch.status == EpochStatus.INVALIDATED.value
    assert obs.epoch.ended_at == T1


def test_an_unchanged_configuration_lets_the_epoch_continue(stores):
    obs = _start(stores)
    assert obs.verify_provenance(_prov(), at=T1) == ()
    assert obs.epoch.status == EpochStatus.OPEN.value
    assert obs.epoch.ended_at is None


def test_a_cosmetic_field_change_does_not_invalidate(stores):
    """Not every difference is material — branch name is bookkeeping."""
    assert invalidation_for(_prov(), _prov(branch="other-branch")) == ()
    assert invalidation_for(_prov(), _prov(qualification_ref="requalified")) == ()


def test_every_invalidating_field_maps_to_a_named_reason():
    from saathi.platform.tg.observation_epoch import INVALIDATING_FIELDS

    valid = {r.value for r in InvalidationReason}
    for f, reason in INVALIDATING_FIELDS.items():
        assert reason.value in valid, f


# ══ the observer cannot touch what it observes ══════════════════════════════
def test_the_observer_has_no_retuning_or_promotion_surface():
    """NO_AUTOMATIC_RETUNING / NO_AUTOMATIC_LIVE_PROMOTION, structurally.

    The guarantee is an ABSENCE, so it is checked by parsing for the absence
    rather than by trusting a docstring.
    """
    tree = ast.parse(SRC.read_text())
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    forbidden = {"tune", "retune", "promote", "set_parameter", "set_threshold",
                 "switch_strategy", "adjust", "optimize", "rebalance", "calibrate"}
    assert not (forbidden & names), forbidden & names

    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    banned = {"record_fill", "record_blocked", "submit", "place", "execute",
              "consume", "approve", "set_status", "force_state", "promote"}
    assert not (banned & called), banned & called


def test_the_observer_imports_no_execution_authority():
    tree = ast.parse(SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("broker", "binance", "venue", "fund_ledger", "execution", "oms")
    assert not [m for m in mods if any(b in m.lower() for b in banned)], mods


def test_a_degraded_verdict_is_recorded_and_left_alone(stores):
    """The observer's job on bad news is to write it down, not to act."""
    obs = _start(stores)
    obs.checkpoint(CheckpointKind.WINDOW, at=T1, health="DEGRADED",
                   note="strategy degraded; no action taken")
    cp = obs.epoch.checkpoints[-1]
    assert cp.health == "DEGRADED"
    assert obs.epoch.status == EpochStatus.OPEN.value
    assert obs.epoch.provenance["strategy_version"] == "btc-mean-reversion@frozen-1"


def test_an_epoch_never_claims_execution_authority(stores):
    assert _start(stores).epoch.to_public()["authorizes_execution"] is False


# ══ checkpoints point at evidence, they do not copy it ══════════════════════
def test_checkpoints_reference_the_session_and_summarise_it(stores):
    _, sessions = stores
    obs = _start(stores)
    sid = obs.epoch.session_id
    sessions.append_event(sid, 1, ShadowEventKind.SIGNAL, {"i": 1}, observed_at=T0)
    sessions.append_event(sid, 2, ShadowEventKind.HYPOTHETICAL_FILL, {"i": 1}, observed_at=T0)
    sessions.record_fill(sid, 2, symbol="BTCUSDT", side="BUY", quantity="1",
                         reference_price="100", fill_price="100", fee="1")

    cp = obs.checkpoint(CheckpointKind.WINDOW, at=T1)
    assert cp.session_id == sid
    assert cp.counts == {"events": 2, "fills": 1, "signals": 1, "counterfactuals": 0}


def test_a_checkpoint_that_cannot_count_still_records_the_fault(stores):
    """Losing the checkpoint would lose the fault it was trying to report."""
    store, _ = stores

    class Broken:
        def events(self, _):
            raise RuntimeError("session store unavailable")

    obs = ShadowObserver(store, Broken(), epoch=ObservationEpoch(
        epoch_id="e1", provenance_fingerprint="f", provenance=vars(_prov()) or {},
        started_at=T0, session_id="s1"))
    cp = obs.checkpoint(CheckpointKind.FAULT, at=T1, note="store down")
    assert cp.counts == {"error": "RuntimeError"}
    assert cp.note == "store down"


def test_faults_are_recorded_not_only_successes(stores):
    obs = _start(stores)
    for kind, note in [(CheckpointKind.FAULT, "feed disconnected"),
                       (CheckpointKind.FAULT, "reconciliation required"),
                       (CheckpointKind.RESTART, "process restarted")]:
        obs.checkpoint(kind, at=T1, note=note)
    kinds = [c.kind for c in obs.epoch.checkpoints]
    assert kinds.count(CheckpointKind.FAULT.value) == 2
    assert CheckpointKind.RESTART.value in kinds


# ══ durability and restart ══════════════════════════════════════════════════
def test_an_epoch_survives_a_restart_without_resetting_anything(stores):
    """Continuity, not restart: no duplicate epoch, no counter reset."""
    store, sessions = stores
    obs = _start(stores)
    eid, sid = obs.epoch.epoch_id, obs.epoch.session_id
    sessions.append_event(sid, 1, ShadowEventKind.SIGNAL, {"i": 1}, observed_at=T0)
    obs.checkpoint(CheckpointKind.WINDOW, at=T0)
    before = len(obs.epoch.checkpoints)

    # New process, same durable state.
    resumed = resume(EpochStore(store.root), sessions, eid)
    assert resumed is not None
    assert resumed.epoch.epoch_id == eid
    assert resumed.epoch.session_id == sid
    assert resumed.epoch.started_at == T0
    assert len(resumed.epoch.checkpoints) == before
    assert resumed.epoch.status == EpochStatus.OPEN.value

    resumed.checkpoint(CheckpointKind.RESTART, at=T1, note="resumed after restart")
    assert len(resumed.epoch.checkpoints) == before + 1
    # And exactly one epoch exists — a restart must not fork the record.
    assert EpochStore(store.root).list_epochs() == (eid,)


def test_a_restart_does_not_invent_a_fresh_healthy_state(stores):
    store, sessions = stores
    obs = _start(stores)
    obs.checkpoint(CheckpointKind.WINDOW, at=T0, health="DEGRADED")
    resumed = resume(EpochStore(store.root), sessions, obs.epoch.epoch_id)
    assert resumed.epoch.checkpoints[-1].health == "DEGRADED"


def test_a_resumed_epoch_still_detects_configuration_drift(stores):
    store, sessions = stores
    obs = _start(stores)
    resumed = resume(EpochStore(store.root), sessions, obs.epoch.epoch_id)
    reasons = resumed.verify_provenance(_prov(code_sha="different"), at=T1)
    assert InvalidationReason.CODE_SHA_CHANGED.value in reasons


def test_manifests_are_written_atomically_and_privately(stores, tmp_path):
    store, _ = stores
    obs = _start(stores)
    path = store._path(obs.epoch.epoch_id)
    assert path.exists()
    assert oct(path.stat().st_mode)[-3:] == "600"
    json.loads(path.read_text())              # parses
    assert not list(store.root.glob("*.tmp"))  # no temp residue


def test_an_unsafe_epoch_id_is_refused(stores):
    store, _ = stores
    for bad in ["../escape", "a/b", "..", "with space", ""]:
        with pytest.raises(ValueError):
            store._path(bad)


def test_a_missing_epoch_resumes_as_none(stores):
    store, sessions = stores
    assert resume(store, sessions, "epoch-does-not-exist") is None


# ══ close ═══════════════════════════════════════════════════════════════════
def test_closing_an_epoch_stamps_it_and_writes_a_final_checkpoint(stores):
    obs = _start(stores)
    epoch = obs.close(at=T1, note="planned close")
    assert epoch.status == EpochStatus.CLOSED.value
    assert epoch.ended_at == T1
    assert epoch.checkpoints[-1].kind == CheckpointKind.EPOCH_CLOSE.value


def test_closing_an_invalidated_epoch_does_not_relabel_it_as_clean(stores):
    """An invalidated epoch must not be laundered into a closed one."""
    obs = _start(stores)
    obs.verify_provenance(_prov(strategy_version="frozen-2"), at=T1)
    epoch = obs.close(at=T1)
    assert epoch.status == EpochStatus.INVALIDATED.value
    assert epoch.invalidation_reasons


def test_limitations_are_carried_on_the_manifest(stores):
    obs = _start(stores)
    assert "no real orders" in obs.epoch.limitations
    assert "no private account" in obs.epoch.limitations
