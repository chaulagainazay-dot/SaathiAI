"""M228 — Simulated Connection State Machine.

Deterministic readiness states. No socket/HTTP to real providers.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import ConnectionState
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid
from saathi.platform.tg.broker_readiness.transport import (
    TransportGuard,
    TransportGuardError,
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
)


class ConnectionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


_TRANSITIONS: dict[ConnectionState, set[ConnectionState]] = {
    ConnectionState.NOT_CONFIGURED: {
        ConnectionState.METADATA_PROPOSED,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.METADATA_PROPOSED: {
        ConnectionState.UNDER_REVIEW,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.UNDER_REVIEW: {
        ConnectionState.SIMULATION_APPROVED,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.SIMULATION_APPROVED: {
        ConnectionState.SIMULATED_CONNECTING,
        ConnectionState.SIMULATED_REVOKED,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.SIMULATED_CONNECTING: {
        ConnectionState.SIMULATED_CONNECTED_READ_ONLY,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.SIMULATED_RATE_LIMITED,
        ConnectionState.SIMULATED_DISCONNECTED,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.SIMULATED_CONNECTED_READ_ONLY: {
        ConnectionState.SIMULATED_DEGRADED,
        ConnectionState.SIMULATED_RATE_LIMITED,
        ConnectionState.SIMULATED_EXPIRED,
        ConnectionState.SIMULATED_REVOKED,
        ConnectionState.SIMULATED_DISCONNECTED,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.SIMULATED_DEGRADED: {
        ConnectionState.SIMULATED_CONNECTED_READ_ONLY,
        ConnectionState.SIMULATED_DISCONNECTED,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.SIMULATED_REVOKED,
    },
    ConnectionState.SIMULATED_RATE_LIMITED: {
        ConnectionState.SIMULATED_CONNECTED_READ_ONLY,
        ConnectionState.SIMULATED_DISCONNECTED,
        ConnectionState.SIMULATED_FAILED_SAFE,
    },
    ConnectionState.SIMULATED_EXPIRED: {
        ConnectionState.SIMULATED_DISCONNECTED,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.NOT_CONFIGURED,
    },
    ConnectionState.SIMULATED_REVOKED: {
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.SIMULATED_DISCONNECTED,
        # no auto-reconnect
    },
    ConnectionState.SIMULATED_DISCONNECTED: {
        ConnectionState.SIMULATED_CONNECTING,  # only if not security_failure
        ConnectionState.SIMULATION_APPROVED,
        ConnectionState.SIMULATED_FAILED_SAFE,
        ConnectionState.REAL_CONNECTION_FORBIDDEN,
    },
    ConnectionState.SIMULATED_FAILED_SAFE: {
        # manual review only — no auto transition to connected
        ConnectionState.NOT_CONFIGURED,
        ConnectionState.UNDER_REVIEW,
    },
    ConnectionState.REAL_CONNECTION_FORBIDDEN: set(),
}


class SimulatedConnectionMachine:
    def __init__(self, store: ReadinessStore, transport: TransportGuard):
        self.store = store
        self.transport = transport

    def create_session(
        self,
        provider_id: str = "sim.readonly.fixture",
        *,
        credential_id: str = "",
        actor: str = "system",
    ) -> dict[str, Any]:
        sid = _uid("sess")
        now = time.time()
        self.store.execute(
            """INSERT INTO br_sessions(
                id, provider_id, credential_id, state, rate_limit_json, clock_skew_sec,
                heartbeat_at, snapshot_fingerprint, auto_reconnect_allowed,
                security_failure, detail_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sid, provider_id, credential_id,
                ConnectionState.NOT_CONFIGURED.value,
                json.dumps({"remaining": 100, "limit": 100}),
                0, None, "", 0, 0,
                json.dumps({"actor": actor}),
                now, now,
            ),
        )
        self._event(sid, "created", "", ConnectionState.NOT_CONFIGURED.value, {})
        return self.get(sid)

    def get(self, session_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM br_sessions WHERE id=?", (session_id,))
        if not row:
            raise ConnectionError("SESSION_NOT_FOUND", session_id)
        return self._public(row)

    def list_sessions(self) -> list[dict[str, Any]]:
        return [self._public(r) for r in self.store.fetchall(
            "SELECT * FROM br_sessions ORDER BY created_at DESC"
        )]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "provider_id": row["provider_id"],
            "credential_id": row["credential_id"],
            "state": row["state"],
            "rate_limit": json.loads(row["rate_limit_json"] or "{}"),
            "clock_skew_sec": row["clock_skew_sec"],
            "heartbeat_at": row["heartbeat_at"],
            "snapshot_fingerprint": row["snapshot_fingerprint"],
            "auto_reconnect_allowed": bool(row["auto_reconnect_allowed"]),
            "security_failure": bool(row["security_failure"]),
            "detail": json.loads(row["detail_json"] or "{}"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "real_transport": False,
            "simulation_only": True,
        }

    def transition(
        self,
        session_id: str,
        to_state: str,
        *,
        reason: str = "",
        force: bool = False,
        mark_security_failure: bool = False,
    ) -> dict[str, Any]:
        sess = self.get(session_id)
        current = ConnectionState(sess["state"])
        target = ConnectionState(to_state)

        if target == ConnectionState.REAL_CONNECTION_FORBIDDEN:
            mark_security_failure = True

        allowed = _TRANSITIONS.get(current, set())
        if target not in allowed and not force and target != ConnectionState.REAL_CONNECTION_FORBIDDEN:
            raise ConnectionError(
                "INVALID_CONNECTION_TRANSITION",
                f"Cannot transition {current.value} → {target.value}",
            )

        # Block auto-reconnect after security failure
        if (
            current in (ConnectionState.SIMULATED_REVOKED, ConnectionState.SIMULATED_FAILED_SAFE)
            or sess["security_failure"]
        ) and target == ConnectionState.SIMULATED_CONNECTING:
            raise ConnectionError(
                "AUTO_RECONNECT_AFTER_SECURITY_FAILURE_FORBIDDEN",
                "Automatic reconnection after security failure is prohibited.",
            )

        now = time.time()
        security = 1 if (mark_security_failure or sess["security_failure"]) else 0
        auto_reconnect = 0 if security else sess["auto_reconnect_allowed"]
        detail = {**sess["detail"], "last_reason": reason}

        self.store.execute(
            """UPDATE br_sessions SET state=?, security_failure=?, auto_reconnect_allowed=?,
               detail_json=?, updated_at=?, heartbeat_at=? WHERE id=?""",
            (
                target.value, security, auto_reconnect,
                json.dumps(detail), now,
                now if target == ConnectionState.SIMULATED_CONNECTED_READ_ONLY else sess["heartbeat_at"],
                session_id,
            ),
        )
        self._event(session_id, "transition", current.value, target.value, {"reason": reason})
        return self.get(session_id)

    def simulate_connect_read_only(
        self,
        session_id: str,
        *,
        real_url: str | None = None,
    ) -> dict[str, Any]:
        """Happy path to SIMULATED_CONNECTED_READ_ONLY. Blocks real URLs."""
        if real_url:
            try:
                self.transport.assert_allowed(real_url)
            except TransportGuardError as e:
                self.transition(
                    session_id, ConnectionState.REAL_CONNECTION_FORBIDDEN.value,
                    reason=e.message, mark_security_failure=True, force=True,
                )
                raise ConnectionError(e.code, e.message) from e

        path = [
            ConnectionState.METADATA_PROPOSED,
            ConnectionState.UNDER_REVIEW,
            ConnectionState.SIMULATION_APPROVED,
            ConnectionState.SIMULATED_CONNECTING,
            ConnectionState.SIMULATED_CONNECTED_READ_ONLY,
        ]
        sess = self.get(session_id)
        for state in path:
            if ConnectionState(sess["state"]) == state:
                continue
            # Capability negotiation, permission inspection, clock sync, snapshot, heartbeat
            events = {
                ConnectionState.METADATA_PROPOSED: "metadata_proposed",
                ConnectionState.UNDER_REVIEW: "permission_inspection",
                ConnectionState.SIMULATION_APPROVED: "capability_negotiation",
                ConnectionState.SIMULATED_CONNECTING: "connection_initiation",
                ConnectionState.SIMULATED_CONNECTED_READ_ONLY: "initial_account_snapshot+heartbeat",
            }
            sess = self.transition(session_id, state.value, reason=events.get(state, ""))
            if state == ConnectionState.SIMULATED_CONNECTED_READ_ONLY:
                self.store.execute(
                    """UPDATE br_sessions SET rate_limit_json=?, clock_skew_sec=?,
                       snapshot_fingerprint=?, updated_at=? WHERE id=?""",
                    (
                        json.dumps({"remaining": 99, "limit": 100, "header": "X-RateLimit-Remaining: 99"}),
                        0.0,
                        "sim-snap-fp-" + session_id[-8:],
                        time.time(),
                        session_id,
                    ),
                )
                sess = self.get(session_id)
        return sess

    def simulate_event(self, session_id: str, event: str) -> dict[str, Any]:
        """Simulate operational events (timeout, outage, etc.)."""
        mapping = {
            "network_timeout": ConnectionState.SIMULATED_DISCONNECTED,
            "provider_outage": ConnectionState.SIMULATED_DEGRADED,
            "rate_limit": ConnectionState.SIMULATED_RATE_LIMITED,
            "session_expiry": ConnectionState.SIMULATED_EXPIRED,
            "credential_expiry": ConnectionState.SIMULATED_EXPIRED,
            "credential_revocation": ConnectionState.SIMULATED_REVOKED,
            "malformed_response": ConnectionState.SIMULATED_FAILED_SAFE,
            "permission_mutation": ConnectionState.SIMULATED_FAILED_SAFE,
            "unexpected_write_permission": ConnectionState.SIMULATED_FAILED_SAFE,
            "provider_identity_mismatch": ConnectionState.SIMULATED_FAILED_SAFE,
            "certificate_failure": ConnectionState.SIMULATED_FAILED_SAFE,
            "ip_allowlist_mismatch": ConnectionState.SIMULATED_FAILED_SAFE,
            "heartbeat": ConnectionState.SIMULATED_CONNECTED_READ_ONLY,
            "reconnect": ConnectionState.SIMULATED_CONNECTING,
            "backoff": ConnectionState.SIMULATED_CONNECTING,
            "real_connection_attempt": ConnectionState.REAL_CONNECTION_FORBIDDEN,
        }
        target = mapping.get(event)
        if target is None:
            raise ConnectionError("UNKNOWN_SIM_EVENT", event)
        security = event in (
            "malformed_response", "permission_mutation", "unexpected_write_permission",
            "provider_identity_mismatch", "certificate_failure", "ip_allowlist_mismatch",
            "credential_revocation", "real_connection_attempt",
        )
        if event == "real_connection_attempt":
            try:
                self.transport.assert_allowed("https://api.binance.com/api/v3/account")
            except TransportGuardError:
                pass
            return self.transition(
                session_id, target.value, reason=event,
                mark_security_failure=True, force=True,
            )
        force = security or event in ("network_timeout", "session_expiry", "credential_expiry", "rate_limit", "provider_outage")
        return self.transition(
            session_id, target.value, reason=event,
            mark_security_failure=security, force=force,
        )

    def _event(self, sid: str, event: str, frm: str, to: str, detail: dict) -> None:
        self.store.execute(
            """INSERT INTO br_session_events(id, session_id, event, from_state, to_state, detail_json, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (_uid("sev"), sid, event, frm, to, json.dumps(detail), time.time()),
        )


__all__ = ["SimulatedConnectionMachine", "ConnectionError"]
