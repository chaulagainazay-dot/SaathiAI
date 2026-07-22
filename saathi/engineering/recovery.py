"""M20.5 — Engineering session recovery (stale leases, crash windows, checkpoints).

Does not resume arbitrary agent processes. It reconciles durable state so the
operator or orchestrator can continue safely.

Does not replace harness run_ledger.reconcile_*.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.engineering.evidence import IntegrityEvidenceStore
from saathi.engineering.session_ledger import (
    TERMINAL_SESSION_STATUSES,
    SessionLedger,
)
from saathi.engineering.store import EngineeringStore

ACTIVE = frozenset({
    "pending", "starting", "running", "stalled", "awaiting_approval", "paused",
})


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except Exception:
        return False


@dataclass
class RecoveryAction:
    session_id: str
    action: str  # reclaim_lease | mark_crashed | resume_ready | none | quarantine_state
    reason: str
    prior_status: str = ""
    new_status: str = ""
    checkpoint_phase: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryReport:
    scanned: int = 0
    actions: list[RecoveryAction] = field(default_factory=list)
    chain_ok: bool = True
    ledger_events: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "actions": [a.to_dict() for a in self.actions],
            "chain_ok": self.chain_ok,
            "ledger_events": self.ledger_events,
            "notes": self.notes,
        }


class SessionRecovery:
    def __init__(
        self,
        store: EngineeringStore,
        *,
        ledger: Optional[SessionLedger] = None,
        evidence: Optional[IntegrityEvidenceStore] = None,
        now_fn: Callable[[], float] | None = None,
        pid_alive_fn: Callable[[int], bool] | None = None,
    ):
        self.store = store
        self.ledger = ledger or SessionLedger(store.root)
        self.evidence = evidence or IntegrityEvidenceStore(store.root, self.ledger)
        self.now = now_fn or time.time
        self.pid_alive = pid_alive_fn or _pid_alive

    def scan(self, *, apply: bool = True) -> RecoveryReport:
        """Scan sessions + ledger; optionally apply recovery actions."""
        report = RecoveryReport()
        chain = self.ledger.verify_chain()
        report.chain_ok = bool(chain.get("ok"))
        report.ledger_events = int(chain.get("events") or 0)
        if not report.chain_ok:
            report.notes.append(f"ledger_chain_broken:{chain.get('error')}")

        self.ledger.append(
            "recovery_scan",
            payload={"apply": apply, "chain_ok": report.chain_ok},
        )

        sessions = self.store.list_sessions(active_only=False)
        report.scanned = len(sessions)
        now = self.now()

        for sess in sessions:
            sid = str(sess.get("session_id") or "")
            status = str(sess.get("status") or "")
            if status in TERMINAL_SESSION_STATUSES:
                continue

            actions_for = []

            # Stale lease
            lease = float(sess.get("lease_until") or 0)
            if status in ACTIVE and lease and lease < now:
                actions_for.append(RecoveryAction(
                    session_id=sid,
                    action="reclaim_lease",
                    reason="lease_expired",
                    prior_status=status,
                    new_status="terminated",
                ))

            # Missing owner process while running
            owner = int(sess.get("owner_pid") or 0)
            if status in {"running", "starting", "stalled"} and owner and not self.pid_alive(owner):
                actions_for.append(RecoveryAction(
                    session_id=sid,
                    action="mark_crashed",
                    reason="owner_process_missing",
                    prior_status=status,
                    new_status="crashed",
                ))

            # Checkpoint resume candidate (paused / stalled with last checkpoint)
            cps = self.store.checkpoints_for(session_id=sid)
            if status in {"paused", "stalled"} and cps:
                last = cps[-1]
                actions_for.append(RecoveryAction(
                    session_id=sid,
                    action="resume_ready",
                    reason="checkpoint_available",
                    prior_status=status,
                    new_status="ready_to_resume",
                    checkpoint_phase=str(last.get("phase") or ""),
                ))

            for act in actions_for:
                report.actions.append(act)
                if not apply:
                    continue
                self._apply(sess, act)

        return report

    def _apply(self, sess: dict[str, Any], act: RecoveryAction) -> None:
        sid = act.session_id
        now = self.now()
        if act.action == "reclaim_lease":
            sess["status"] = "terminated"
            sess["stop_reason"] = "stale_lease"
            sess["updated_at"] = now
            self.store.put_session(sess)
            self.ledger.append(
                "recovery_action",
                session_id=sid,
                payload=act.to_dict(),
            )
            self.ledger.append(
                "stop",
                session_id=sid,
                payload={"reason": "stale_lease", "via": "recovery"},
            )
        elif act.action == "mark_crashed":
            sess["status"] = "crashed"
            sess["stop_reason"] = "owner_process_missing"
            sess["updated_at"] = now
            self.store.put_session(sess)
            self.ledger.append(
                "recovery_action",
                session_id=sid,
                payload=act.to_dict(),
            )
            self.ledger.append(
                "session_status",
                session_id=sid,
                payload={"status": "crashed", "reason": "owner_process_missing"},
            )
        elif act.action == "resume_ready":
            # Do not auto-restart agents — mark for operator resume
            sess["recovery"] = {
                "ready_to_resume": True,
                "checkpoint_phase": act.checkpoint_phase,
                "scanned_at": now,
            }
            sess["updated_at"] = now
            self.store.put_session(sess)
            self.ledger.append(
                "recovery_action",
                session_id=sid,
                payload=act.to_dict(),
            )

    def resume_plan(self, session_id: str) -> dict[str, Any]:
        """Describe how an operator may resume; never auto-launches agents."""
        sess = self.store.get_session(session_id)
        if not sess:
            return {"ok": False, "error": "session_not_found"}
        cps = self.store.checkpoints_for(session_id=session_id)
        timeline = self.ledger.session_timeline(session_id)
        last_integrity = [
            e for e in timeline if e.get("event_type") in (
                "integrity_baseline", "integrity_check", "integrity_violation",
            )
        ]
        return {
            "ok": True,
            "session_id": session_id,
            "status": sess.get("status"),
            "last_checkpoint": cps[-1] if cps else None,
            "checkpoint_count": len(cps),
            "ledger_events": len(timeline),
            "last_integrity_event": last_integrity[-1] if last_integrity else None,
            "recovery": sess.get("recovery") or {},
            "next_action": (
                "operator_may_relaunch_with_same_item_and_checkpoint"
                if cps
                else "no_checkpoint_relaunch_from_item_start"
            ),
            "auto_launch": False,
        }


def recover_store(
    store: EngineeringStore,
    *,
    apply: bool = True,
) -> dict[str, Any]:
    """Convenience entry for CLI / orchestrator."""
    eng = SessionRecovery(store)
    report = eng.scan(apply=apply)
    # also reclaim via store helper for consistency
    if apply:
        reclaimed = store.reclaim_stale_leases()
        if reclaimed:
            report.notes.append(f"store_reclaim:{len(reclaimed)}")
    return report.to_dict()
