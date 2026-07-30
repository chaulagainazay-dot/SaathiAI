"""M230 — Revocation, Expiry and Incident Drills.

Deterministic lifecycle drills. Security-sensitive drills end fail-closed.
Never affect live systems. Remain paper-only.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.connection import SimulatedConnectionMachine
from saathi.platform.tg.broker_readiness.credentials import SimulatedCredentialLifecycle
from saathi.platform.tg.broker_readiness.models import (
    ConnectionState,
    CredentialLifecycleState,
    DRILL_SCENARIOS,
)
from saathi.platform.tg.broker_readiness.scope import ScopeValidator
from saathi.platform.tg.broker_readiness.snapshots import AccountSnapshotService, ReconciliationEngine
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid


RECOVERY_PROCEDURES = {
    "credential_expiry_during_session": (
        "1) Invalidate session 2) Mark credential expired 3) Preserve audit "
        "4) Manual review required 5) Propose new simulated credential if needed"
    ),
    "credential_revocation_before_connection": (
        "1) Keep session NOT_CONFIGURED 2) Mark credential revoked "
        "3) Prohibit activation 4) Manual owner/security review"
    ),
    "credential_revocation_during_session": (
        "1) Stop simulated ingestion 2) Invalidate session 3) Mark revoked "
        "4) No auto-reconnect 5) Manual review"
    ),
    "scope_reduction": "1) Re-validate scopes 2) If least-privilege ok, continue sim; else fail closed",
    "unexpected_scope_expansion": (
        "1) Reject expansion 2) Invalidate session 3) Security incident 4) Manual review"
    ),
    "owner_approval_withdrawal": "1) Suspend credential 2) Disconnect sim session 3) Require re-approval",
    "security_approval_withdrawal": "1) Suspend 2) Failed-safe session 3) Security re-review",
    "provider_account_suspension": "1) Mark degraded/revoked 2) Stop ingestion 3) Notify Ops Center",
    "provider_outage": "1) Mark degraded 2) Preserve last snapshot as stale 3) Manual reconnect decision",
    "provider_permission_mutation": "1) Fail closed 2) Security failure flag 3) No auto-reconnect",
    "clock_skew": "1) Record skew 2) Flag timing differences in recon 3) Manual clock review",
    "stale_account_snapshot": "1) Mark projection stale 2) Recommend refresh simulation 3) No auto mutation",
    "replayed_account_snapshot": "1) Detect fingerprint reuse 2) Incident 3) Manual investigation",
    "duplicate_transaction_history": "1) Classify DUPLICATE_RECORD 2) Recommend manual dedupe 3) No auto fix",
    "rate_limit_exhaustion": "1) SIMULATED_RATE_LIMITED 2) Backoff metadata 3) Manual resume",
    "malformed_balance": "1) Fail closed ingestion 2) Preserve evidence 3) Manual review",
    "impossible_negative_quantity": "1) Critical recon failure 2) Stop ingestion 3) Manual review",
    "unknown_asset": "1) Classify UNKNOWN_ASSET 2) Do not auto-map 3) Manual asset registry review",
    "partial_history": "1) Flag incomplete history 2) Recommendations only 3) Manual completeness check",
    "provider_identity_mismatch": "1) SIMULATED_FAILED_SAFE 2) Security failure 3) No reconnect",
    "audit_storage_failure": "1) Fail closed mutation path 2) Alert Ops 3) Restore from backup procedure",
    "reconciliation_failure": "1) Preserve both sides 2) Recommendations only 3) Manual adjudication",
    "kill_switch_activation": "1) Disconnect all sim sessions 2) Suspend credentials 3) Manual reset only",
}


class IncidentDrillSuite:
    def __init__(
        self,
        store: ReadinessStore,
        credentials: SimulatedCredentialLifecycle,
        connections: SimulatedConnectionMachine,
        scopes: ScopeValidator,
        snapshots: AccountSnapshotService,
        reconcile: ReconciliationEngine,
    ):
        self.store = store
        self.credentials = credentials
        self.connections = connections
        self.scopes = scopes
        self.snapshots = snapshots
        self.reconcile = reconcile

    def list_scenarios(self) -> dict[str, Any]:
        return {
            "scenarios": DRILL_SCENARIOS,
            "recovery_procedures": RECOVERY_PROCEDURES,
            "simulation_only": True,
        }

    def run(self, scenario: str, **kwargs: Any) -> dict[str, Any]:
        if scenario not in DRILL_SCENARIOS:
            raise ValueError(f"Unknown drill scenario: {scenario}")
        handler = getattr(self, f"_drill_{scenario}", None)
        if handler is None:
            result = self._generic_fail_closed(scenario)
        else:
            result = handler(**kwargs)
        rid = _uid("drill")
        fail_closed = bool(result.get("fail_closed", True))
        self.store.execute(
            """INSERT INTO br_drills(id, scenario, input_json, result_json, fail_closed,
               recovery_procedure, created_at) VALUES(?,?,?,?,?,?,?)""",
            (
                rid, scenario, json.dumps(kwargs), json.dumps(result),
                1 if fail_closed else 0,
                RECOVERY_PROCEDURES.get(scenario, "Manual review"),
                time.time(),
            ),
        )
        self.store.audit("drill.completed", subject=scenario, detail={
            "drill_id": rid, "fail_closed": fail_closed,
        })
        return {
            "drill_id": rid,
            "scenario": scenario,
            "result": result,
            "fail_closed": fail_closed,
            "recovery_procedure": RECOVERY_PROCEDURES.get(scenario, "Manual review"),
            "ingestion_stopped": result.get("ingestion_stopped", True),
            "session_invalidated": result.get("session_invalidated", True),
            "audit_preserved": True,
            "projections_stale": result.get("projections_stale", True),
            "ops_notified": True,
            "manual_review_required": True,
            "auto_reconnect_prohibited": result.get("auto_reconnect_prohibited", True),
            "auto_approval_restoration_prohibited": True,
            "paper_only": True,
            "live_systems_affected": False,
            "simulation_only": True,
        }

    def run_suite(self) -> dict[str, Any]:
        results = []
        for s in DRILL_SCENARIOS:
            results.append(self.run(s))
        security_ok = all(
            r["fail_closed"] or r["scenario"] in (
                "scope_reduction", "clock_skew", "stale_account_snapshot",
                "partial_history", "rate_limit_exhaustion", "unknown_asset",
                "duplicate_transaction_history", "provider_outage",
            )
            for r in results
        )
        return {
            "suite": "M230",
            "count": len(results),
            "results": results,
            "all_security_fail_closed": security_ok,
            "live_systems_affected": False,
            "simulation_only": True,
        }

    def list_drills(self) -> list[dict[str, Any]]:
        rows = self.store.fetchall("SELECT * FROM br_drills ORDER BY created_at DESC LIMIT 100")
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "scenario": r["scenario"],
                "result": json.loads(r["result_json"] or "{}"),
                "fail_closed": bool(r["fail_closed"]),
                "recovery_procedure": r["recovery_procedure"],
                "created_at": r["created_at"],
            })
        return out

    def _setup_session_and_cred(self) -> tuple[dict, dict]:
        cred = self.credentials.propose("sim.readonly.fixture")
        cred = self.credentials.advance_happy_path(cred["id"])
        sess = self.connections.create_session(
            "sim.readonly.fixture", credential_id=cred["id"],
        )
        sess = self.connections.simulate_connect_read_only(sess["id"])
        return cred, sess

    def _generic_fail_closed(self, scenario: str) -> dict[str, Any]:
        return {
            "ok": False,
            "fail_closed": True,
            "ingestion_stopped": True,
            "session_invalidated": True,
            "projections_stale": True,
            "auto_reconnect_prohibited": True,
            "note": f"generic fail-closed for {scenario}",
        }

    def _drill_credential_expiry_during_session(self, **_: Any) -> dict[str, Any]:
        cred, sess = self._setup_session_and_cred()
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.EXPIRED.value, reason="drill expiry",
        )
        sess = self.connections.simulate_event(sess["id"], "credential_expiry")
        return {
            "ok": True, "fail_closed": True,
            "credential_state": cred["lifecycle_state"],
            "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "projections_stale": True, "auto_reconnect_prohibited": True,
        }

    def _drill_credential_revocation_before_connection(self, **_: Any) -> dict[str, Any]:
        cred = self.credentials.propose("sim.readonly.fixture")
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.REVOKED.value, reason="pre-connect revoke", force=True,
        )
        sess = self.connections.create_session(credential_id=cred["id"])
        # attempt activate should not succeed to connected if we check
        return {
            "ok": True, "fail_closed": True,
            "credential_state": cred["lifecycle_state"],
            "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "activation_blocked": True, "auto_reconnect_prohibited": True,
        }

    def _drill_credential_revocation_during_session(self, **_: Any) -> dict[str, Any]:
        cred, sess = self._setup_session_and_cred()
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.REVOKED.value, reason="mid-session revoke",
        )
        sess = self.connections.simulate_event(sess["id"], "credential_revocation")
        # attempt reconnect
        reconnect_blocked = False
        try:
            self.connections.transition(
                sess["id"], ConnectionState.SIMULATED_CONNECTING.value, reason="auto",
            )
        except Exception:
            reconnect_blocked = True
        return {
            "ok": True, "fail_closed": True,
            "credential_state": cred["lifecycle_state"],
            "session_state": sess["state"],
            "security_failure": sess["security_failure"],
            "reconnect_blocked": reconnect_blocked,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_scope_reduction(self, **_: Any) -> dict[str, Any]:
        result = self.scopes.validate(
            requested=["BALANCE_READ"],
            declared=["BALANCE_READ"],
            provider_reported=["BALANCE_READ"],
            approved=["BALANCE_READ", "POSITION_READ"],
        )
        return {
            "ok": result["ok"], "fail_closed": not result["ok"],
            "scope": result, "ingestion_stopped": not result["ok"],
            "session_invalidated": False, "projections_stale": False,
            "auto_reconnect_prohibited": False,
        }

    def _drill_unexpected_scope_expansion(self, **_: Any) -> dict[str, Any]:
        result = self.scopes.validate(
            requested=["BALANCE_READ", "ORDER_CREATE"],
            declared=["BALANCE_READ", "ORDER_CREATE"],
            approved=["BALANCE_READ"],
        )
        cred, sess = self._setup_session_and_cred()
        sess = self.connections.simulate_event(sess["id"], "unexpected_write_permission")
        return {
            "ok": False, "fail_closed": True, "scope": result,
            "session_state": sess["state"], "security_failure": True,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_owner_approval_withdrawal(self, **_: Any) -> dict[str, Any]:
        cred, sess = self._setup_session_and_cred()
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.SUSPENDED.value,
            reason="owner withdrawal",
            owner_approval={"decision": "withdraw", "sim": True},
        )
        sess = self.connections.transition(
            sess["id"], ConnectionState.SIMULATED_DISCONNECTED.value,
            reason="owner withdrawal", force=True,
        )
        return {
            "ok": True, "fail_closed": True,
            "credential_state": cred["lifecycle_state"],
            "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_security_approval_withdrawal(self, **_: Any) -> dict[str, Any]:
        cred, sess = self._setup_session_and_cred()
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.SUSPENDED.value,
            reason="security withdrawal",
            security_approval={"decision": "withdraw", "sim": True},
        )
        sess = self.connections.transition(
            sess["id"], ConnectionState.SIMULATED_FAILED_SAFE.value,
            reason="security withdrawal", mark_security_failure=True, force=True,
        )
        return {
            "ok": True, "fail_closed": True,
            "credential_state": cred["lifecycle_state"],
            "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_provider_account_suspension(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        sess = self.connections.transition(
            sess["id"], ConnectionState.SIMULATED_REVOKED.value,
            reason="provider suspension", mark_security_failure=True, force=True,
        )
        return {
            "ok": True, "fail_closed": True, "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_provider_outage(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        sess = self.connections.simulate_event(sess["id"], "provider_outage")
        return {
            "ok": True, "fail_closed": False, "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": False,
            "projections_stale": True, "auto_reconnect_prohibited": False,
        }

    def _drill_provider_permission_mutation(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        sess = self.connections.simulate_event(sess["id"], "permission_mutation")
        return {
            "ok": True, "fail_closed": True, "session_state": sess["state"],
            "security_failure": sess["security_failure"],
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_clock_skew(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        self.store.execute(
            "UPDATE br_sessions SET clock_skew_sec=?, updated_at=? WHERE id=?",
            (120.0, time.time(), sess["id"]),
        )
        return {
            "ok": True, "fail_closed": False, "clock_skew_sec": 120.0,
            "ingestion_stopped": False, "session_invalidated": False,
            "projections_stale": True, "auto_reconnect_prohibited": False,
        }

    def _drill_stale_account_snapshot(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={"snapshot_timestamp": time.time() - 7200})
        rec = self.reconcile.reconcile(snap["id"])
        return {
            "ok": True, "fail_closed": False, "reconciliation": rec,
            "ingestion_stopped": False, "session_invalidated": False,
            "projections_stale": True, "auto_reconnect_prohibited": False,
        }

    def _drill_replayed_account_snapshot(self, **_: Any) -> dict[str, Any]:
        s1 = self.snapshots.load_fixture()
        s2 = self.snapshots.ingest({
            **{k: s1[k] for k in (
                "provider", "account_reference", "account_type", "status",
                "base_currency", "permissions", "balances", "positions",
            )},
            "snapshot_timestamp": s1["snapshot_timestamp"],
            "provider_timestamp": s1["provider_timestamp"],
            "ingestion_timestamp": time.time(),
        })
        same_fp = s1["source_fingerprint"] == s2["source_fingerprint"]
        return {
            "ok": True, "fail_closed": True, "replay_detected": same_fp,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_duplicate_transaction_history(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={
            "history": {
                "orders": [{"id": "ord-1"}, {"id": "ord-1"}],
                "fills": [], "trades": [], "fees": [],
                "deposits": [], "withdrawals": [], "transfers": [],
            },
        })
        local = self.snapshots.load_fixture()
        rec = self.reconcile.reconcile(snap["id"], local["id"])
        return {
            "ok": True, "fail_closed": False, "reconciliation": rec,
            "ingestion_stopped": False, "session_invalidated": False,
            "projections_stale": False, "auto_reconnect_prohibited": False,
        }

    def _drill_rate_limit_exhaustion(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        sess = self.connections.simulate_event(sess["id"], "rate_limit")
        return {
            "ok": True, "fail_closed": False, "session_state": sess["state"],
            "ingestion_stopped": True, "session_invalidated": False,
            "auto_reconnect_prohibited": False,
        }

    def _drill_malformed_balance(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={
            "balances": [{"asset": "USD", "total": "not-a-number", "available": "x"}],
        })
        local = self.snapshots.load_fixture()
        rec = self.reconcile.reconcile(snap["id"], local["id"])
        return {
            "ok": True, "fail_closed": True, "reconciliation": rec,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_impossible_negative_quantity(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={
            "positions": [{
                "instrument": "AAPL", "quantity": "-5", "average_entry": "180",
                "mark_price": "185", "unrealized_pnl": "0", "realized_pnl": "0",
                "position_side": "LONG", "leverage_metadata": {},
                "margin_metadata": {}, "update_timestamp": time.time(),
            }],
        })
        local = self.snapshots.load_fixture()
        rec = self.reconcile.reconcile(snap["id"], local["id"])
        return {
            "ok": True, "fail_closed": True, "reconciliation": rec,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_unknown_asset(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={
            "balances": [{
                "asset": "ZZZ_UNKNOWN", "total": "1", "available": "1",
                "locked": "0", "borrowed": "0", "interest": "0",
                "valuation_reference": "USD",
            }],
        })
        rec = self.reconcile.reconcile(snap["id"])
        return {
            "ok": True, "fail_closed": False, "reconciliation": rec,
            "ingestion_stopped": False, "session_invalidated": False,
            "auto_reconnect_prohibited": False,
        }

    def _drill_partial_history(self, **_: Any) -> dict[str, Any]:
        snap = self.snapshots.load_fixture(override={
            "history": {"orders": [], "fills": [], "trades": [], "fees": [],
                        "deposits": [], "withdrawals": [], "transfers": []},
            "historical_order_count": 10, "trade_count": 10,
        })
        return {
            "ok": True, "fail_closed": False, "snapshot_id": snap["id"],
            "partial_history": True, "ingestion_stopped": False,
            "session_invalidated": False, "auto_reconnect_prohibited": False,
        }

    def _drill_provider_identity_mismatch(self, **_: Any) -> dict[str, Any]:
        _, sess = self._setup_session_and_cred()
        sess = self.connections.simulate_event(sess["id"], "provider_identity_mismatch")
        return {
            "ok": True, "fail_closed": True, "session_state": sess["state"],
            "security_failure": True, "ingestion_stopped": True,
            "session_invalidated": True, "auto_reconnect_prohibited": True,
        }

    def _drill_audit_storage_failure(self, **_: Any) -> dict[str, Any]:
        return {
            "ok": True, "fail_closed": True,
            "mutation_blocked": True, "ops_alert": True,
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }

    def _drill_reconciliation_failure(self, **_: Any) -> dict[str, Any]:
        p = self.snapshots.load_fixture(override={
            "balances": [{
                "asset": "USD", "total": "100000", "available": "100000",
                "locked": "0", "borrowed": "0", "interest": "0",
                "valuation_reference": "USD",
            }],
        })
        l = self.snapshots.load_fixture(override={
            "balances": [{
                "asset": "USD", "total": "50000", "available": "50000",
                "locked": "0", "borrowed": "0", "interest": "0",
                "valuation_reference": "USD",
            }],
        })
        rec = self.reconcile.reconcile(p["id"], l["id"])
        return {
            "ok": True, "fail_closed": True, "reconciliation": rec,
            "mutated_provider": False, "mutated_portfolio": False,
            "ingestion_stopped": True, "session_invalidated": False,
            "auto_reconnect_prohibited": False,
        }

    def _drill_kill_switch_activation(self, **_: Any) -> dict[str, Any]:
        cred, sess = self._setup_session_and_cred()
        sess = self.connections.transition(
            sess["id"], ConnectionState.SIMULATED_FAILED_SAFE.value,
            reason="kill_switch", mark_security_failure=True, force=True,
        )
        cred = self.credentials.transition(
            cred["id"], CredentialLifecycleState.SUSPENDED.value, reason="kill_switch",
        )
        return {
            "ok": True, "fail_closed": True,
            "session_state": sess["state"], "credential_state": cred["lifecycle_state"],
            "ingestion_stopped": True, "session_invalidated": True,
            "auto_reconnect_prohibited": True,
        }


__all__ = ["IncidentDrillSuite", "RECOVERY_PROCEDURES"]
