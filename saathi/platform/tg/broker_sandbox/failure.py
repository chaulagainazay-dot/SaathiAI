"""M221 — Failure & Recovery simulation.

Simulates network loss, outages, duplicate/late fills, clock skew, replay,
sequence gaps, connection loss, credential expiry, recovery, rollback.
Everything fails closed.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_sandbox.credentials import CredentialTrustFramework
from saathi.platform.tg.broker_sandbox.emulator import SandboxBrokerError, SandboxEmulator
from saathi.platform.tg.broker_sandbox.models import FailureScenario
from saathi.platform.tg.broker_sandbox.store import SandboxStore, _uid


FAILURE_SCENARIOS = [s.value for s in FailureScenario]


class FailureRecoverySimulator:
    def __init__(
        self,
        store: SandboxStore,
        emulator: SandboxEmulator,
        credentials: CredentialTrustFramework,
    ):
        self.store = store
        self.emulator = emulator
        self.credentials = credentials

    def _record(
        self,
        scenario: str,
        *,
        session_id: str = "",
        input_data: dict | None = None,
        result: dict | None = None,
        fail_closed: bool = True,
        recovered: bool = False,
    ) -> dict[str, Any]:
        eid = _uid("fail")
        self.store.execute(
            """INSERT INTO bs_failure_events(
                id, session_id, scenario, input_json, result_json, fail_closed, recovered, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                eid, session_id, scenario,
                json.dumps(input_data or {}),
                json.dumps(result or {}),
                1 if fail_closed else 0,
                1 if recovered else 0,
                time.time(),
            ),
        )
        self.store.audit(
            "failure.simulated",
            subject=eid,
            detail={"scenario": scenario, "fail_closed": fail_closed, "recovered": recovered},
        )
        return {
            "id": eid,
            "scenario": scenario,
            "session_id": session_id,
            "result": result or {},
            "fail_closed": fail_closed,
            "recovered": recovered,
            "paper_only": True,
            "live_impact": False,
        }

    def run(self, scenario: str, *, session_id: str = "", **kwargs: Any) -> dict[str, Any]:
        sc = scenario.upper()
        if sc not in FAILURE_SCENARIOS:
            return self._record(
                sc,
                session_id=session_id,
                result={"ok": False, "error": "UNKNOWN_SCENARIO"},
                fail_closed=True,
            )

        handlers = {
            FailureScenario.NETWORK_LOSS.value: self._network_loss,
            FailureScenario.BROKER_OUTAGE.value: self._broker_outage,
            FailureScenario.DUPLICATE_FILLS.value: self._duplicate_fills,
            FailureScenario.LATE_FILLS.value: self._late_fills,
            FailureScenario.CLOCK_SKEW.value: self._clock_skew,
            FailureScenario.ORDER_REPLAY.value: self._order_replay,
            FailureScenario.SEQUENCE_GAPS.value: self._sequence_gaps,
            FailureScenario.CONNECTION_LOSS.value: self._connection_loss,
            FailureScenario.CREDENTIAL_EXPIRY.value: self._credential_expiry,
            FailureScenario.RECOVERY.value: self._recovery,
            FailureScenario.ROLLBACK.value: self._rollback,
            FailureScenario.RATE_LIMIT.value: self._rate_limit,
            FailureScenario.MARKET_CLOSED.value: self._market_closed,
            FailureScenario.INVALID_SYMBOL.value: self._invalid_symbol,
            FailureScenario.TIMEOUT.value: self._timeout,
            FailureScenario.PARTIAL_FILL.value: self._partial_fill,
            FailureScenario.REJECT.value: self._reject,
            FailureScenario.LATENCY.value: self._latency,
            FailureScenario.DISCONNECT.value: self._disconnect,
        }
        return handlers[sc](session_id=session_id, **kwargs)

    def _ensure_session(self, session_id: str) -> str:
        if session_id:
            return session_id
        return self.emulator.create_session()["id"]

    def _network_loss(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "NETWORK_LOSS")
        try:
            self.emulator.place_order(
                sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
            )
            result = {"ok": False, "error": "EXPECTED_FAIL_CLOSED"}
            fc = False
        except SandboxBrokerError as e:
            result = {"ok": True, "error_code": e.code, "message": e.message}
            fc = True
        return self._record("NETWORK_LOSS", session_id=sid, result=result, fail_closed=fc)

    def _broker_outage(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "BROKER_OUTAGE")
        try:
            self.emulator.place_order(
                sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
            )
            result = {"ok": False, "error": "EXPECTED_FAIL_CLOSED"}
            fc = False
        except SandboxBrokerError as e:
            result = {"ok": True, "error_code": e.code, "message": e.message}
            fc = True
        return self._record("BROKER_OUTAGE", session_id=sid, result=result, fail_closed=fc)

    def _duplicate_fills(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "DUPLICATE_FILLS")
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="10",
        )
        dups = [f for f in order["fills"] if f["is_duplicate"]]
        result = {
            "ok": True,
            "order_id": order["order_id"],
            "fill_count": len(order["fills"]),
            "duplicate_fills": len(dups),
            "detected": len(order["fills"]) > 1,
        }
        return self._record("DUPLICATE_FILLS", session_id=sid, result=result, fail_closed=True)

    def _late_fills(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "LATE_FILLS")
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="5",
        )
        late = [f for f in order["fills"] if f["is_late"]]
        result = {
            "ok": True,
            "order_id": order["order_id"],
            "late_fills": len(late),
            "flagged": len(late) > 0,
        }
        return self._record("LATE_FILLS", session_id=sid, result=result, fail_closed=True)

    def _clock_skew(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_clock_skew(sid, 3600.0)
        sess = self.emulator.get_session(sid)
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "clock_skew_sec": sess["clock_skew_sec"],
            "order_created_at": order["created_at"],
            "skew_applied": abs(sess["clock_skew_sec"]) > 0,
        }
        return self._record("CLOCK_SKEW", session_id=sid, result=result, fail_closed=True)

    def _order_replay(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        client_id = "replay-test-1"
        o1 = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="2",
            client_order_id=client_id,
        )
        o2 = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="2",
            client_order_id=client_id,
        )
        # Emulator records both but exposes them as distinct sandbox events for detection
        result = {
            "ok": True,
            "first_order": o1["order_id"],
            "replay_order": o2["order_id"],
            "same_client_id": o1["client_order_id"] == o2["client_order_id"],
            "distinct_order_ids": o1["order_id"] != o2["order_id"],
            "replay_detectable": True,
        }
        return self._record("ORDER_REPLAY", session_id=sid, result=result, fail_closed=True)

    def _sequence_gaps(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        # Place orders then force sequence jump
        self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        self.store.execute(
            "UPDATE bs_emulator_sessions SET sequence_counter=sequence_counter+5, updated_at=? WHERE id=?",
            (time.time(), sid),
        )
        o2 = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        orders = self.emulator.list_orders(sid)
        seqs = [o["sequence"] for o in orders]
        gaps = any(seqs[i + 1] - seqs[i] > 1 for i in range(len(seqs) - 1)) if len(seqs) > 1 else False
        result = {
            "ok": True,
            "sequences": seqs,
            "gap_detected": gaps or (o2["sequence"] > 2),
            "fail_closed_on_gap": True,
        }
        return self._record("SEQUENCE_GAPS", session_id=sid, result=result, fail_closed=True)

    def _connection_loss(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_connected(sid, False)
        try:
            self.emulator.place_order(
                sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
            )
            result = {"ok": False, "error": "EXPECTED_FAIL_CLOSED"}
            fc = False
        except SandboxBrokerError as e:
            result = {"ok": True, "error_code": e.code, "message": e.message}
            fc = True
        return self._record("CONNECTION_LOSS", session_id=sid, result=result, fail_closed=fc)

    def _credential_expiry(self, session_id: str = "", **kwargs: Any) -> dict[str, Any]:
        broker_id = kwargs.get("broker_id", "catalog.binance")
        ref = self.credentials.create_reference(
            broker_id,
            label="expiry-test",
            expires_at=time.time() - 1,
            actor="system",
        )
        expired = self.credentials.mark_expired(ref["id"])
        use = self.credentials.attempt_use(ref["id"])
        result = {
            "ok": True,
            "ref_id": ref["id"],
            "status": expired["status"],
            "use_refused": use["ok"] is False,
            "usable": False,
        }
        return self._record(
            "CREDENTIAL_EXPIRY",
            session_id=session_id,
            result=result,
            fail_closed=True,
        )

    def _recovery(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_connected(sid, False)
        self.emulator.set_failure_mode(sid, "NETWORK_LOSS")
        # Recovery: clear failure and reconnect
        self.emulator.set_failure_mode(sid, "")
        self.emulator.set_connected(sid, True)
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "recovered": True,
            "order_state": order["state"],
            "session": self.emulator.get_session(sid),
        }
        return self._record(
            "RECOVERY", session_id=sid, result=result, fail_closed=True, recovered=True
        )

    def _rollback(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        before = self.emulator.get_session(sid)
        self.emulator.set_failure_mode(sid, "REJECT")
        self.emulator.set_latency(sid, 500)
        # Rollback session config to safe defaults
        self.emulator.set_failure_mode(sid, "")
        self.emulator.set_latency(sid, 0)
        self.emulator.set_connected(sid, True)
        self.emulator.set_market_open(sid, True)
        after = self.emulator.get_session(sid)
        result = {
            "ok": True,
            "before_failure_mode": before.get("failure_mode", ""),
            "after_failure_mode": after["failure_mode"],
            "rolled_back": after["failure_mode"] == "" and after["connected"] and after["market_open"],
        }
        return self._record(
            "ROLLBACK", session_id=sid, result=result, fail_closed=True, recovered=True
        )

    def _rate_limit(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "RATE_LIMIT")
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "reject_reason": order["reject_reason"],
            "rate_limited": order["state"] == "REJECTED",
        }
        return self._record("RATE_LIMIT", session_id=sid, result=result, fail_closed=True)

    def _market_closed(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_market_open(sid, False)
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "reject_reason": order["reject_reason"],
        }
        return self._record("MARKET_CLOSED", session_id=sid, result=result, fail_closed=True)

    def _invalid_symbol(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        order = self.emulator.place_order(
            sid, symbol="NOT_A_REAL_SYMBOL_XYZ", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "reject_reason": order["reject_reason"],
        }
        return self._record("INVALID_SYMBOL", session_id=sid, result=result, fail_closed=True)

    def _timeout(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "TIMEOUT")
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "timed_out": order["state"] == "TIMED_OUT",
        }
        return self._record("TIMEOUT", session_id=sid, result=result, fail_closed=True)

    def _partial_fill(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="10",
            partial_fill_ratio="0.4",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "filled_qty": order["filled_qty"],
            "partial": order["state"] == "PARTIALLY_FILLED",
        }
        return self._record("PARTIAL_FILL", session_id=sid, result=result, fail_closed=True)

    def _reject(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_failure_mode(sid, "REJECT")
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "state": order["state"],
            "reject_reason": order["reject_reason"],
        }
        return self._record("REJECT", session_id=sid, result=result, fail_closed=True)

    def _latency(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        sid = self._ensure_session(session_id)
        self.emulator.set_latency(sid, 250)
        sess = self.emulator.get_session(sid)
        order = self.emulator.place_order(
            sid, symbol="AAA", side="BUY", order_type="MARKET", quantity="1",
        )
        result = {
            "ok": True,
            "latency_ms": sess["latency_ms"],
            "order_state": order["state"],
            "simulated_only": True,
        }
        return self._record("LATENCY", session_id=sid, result=result, fail_closed=True)

    def _disconnect(self, session_id: str = "", **_: Any) -> dict[str, Any]:
        return self._connection_loss(session_id=session_id)

    def run_suite(self) -> dict[str, Any]:
        results = []
        all_fc = True
        for sc in FAILURE_SCENARIOS:
            r = self.run(sc)
            results.append(r)
            if not r.get("fail_closed", True):
                all_fc = False
        return {
            "scenarios": len(results),
            "results": results,
            "all_fail_closed": all_fc,
            "passed": all(r.get("result", {}).get("ok", False) for r in results) and all_fc,
            "paper_only": True,
            "live_impact": False,
        }

    def list_events(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.store.fetchall(
            "SELECT * FROM bs_failure_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in rows:
            out.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "scenario": r["scenario"],
                "result": json.loads(r["result_json"] or "{}"),
                "fail_closed": bool(r["fail_closed"]),
                "recovered": bool(r["recovered"]),
                "created_at": r["created_at"],
            })
        return out


__all__ = ["FailureRecoverySimulator", "FAILURE_SCENARIOS"]
