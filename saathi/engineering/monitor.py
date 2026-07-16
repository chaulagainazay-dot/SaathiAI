"""M20.0 — Engineering session progress monitor.

Reuses stuck-run *concepts* from harness run_monitor without a second stack.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from saathi.engineering.models import SessionStatus
from saathi.engineering.store import EngineeringStore

# Policy-violation signal patterns in agent output / command text
_POLICY_PATTERNS = {
    "force_push_attempt": re.compile(r"(?i)git\s+push\s+.*--force|git\s+push\s+-f\b"),
    "merge_attempt": re.compile(r"(?i)git\s+merge\b|gh\s+pr\s+merge\b"),
    "deploy_attempt": re.compile(
        r"(?i)\b(deploy|kubectl\s+apply|terraform\s+apply|fly\s+deploy|vercel\s+deploy)\b"
    ),
    "live_trading_attempt": re.compile(
        r"(?i)(place_order|create_order|execute_trade|binance\.|alpaca\.|/order)"
    ),
    "secret_file_creation": re.compile(
        r"(?i)(\.env\.local|id_rsa|credentials\.json|service.account.*\.json)"
    ),
}


@dataclass
class MonitorSnapshot:
    session_id: str
    status: str
    phase: str = ""
    last_output_time: float = 0.0
    last_checkpoint_time: float = 0.0
    process_healthy: bool = True
    head: str = ""
    branch: str = ""
    changed_files: list[str] = field(default_factory=list)
    repeated_failures: int = 0
    blocked: bool = False
    active_command: str = ""
    elapsed_sec: float = 0.0
    heartbeat_age_sec: float = 0.0
    detections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProgressMonitor:
    def __init__(
        self,
        store: EngineeringStore,
        *,
        stall_timeout_sec: float = 600.0,
        now_fn: Callable[[], float] | None = None,
    ):
        self.store = store
        self.stall_timeout_sec = stall_timeout_sec
        self.now = now_fn or time.time

    def heartbeat(self, session_id: str, **fields: Any) -> dict[str, Any]:
        sess = self.store.get_session(session_id) or {"session_id": session_id}
        sess["session_id"] = session_id
        sess["last_heartbeat"] = self.now()
        sess["last_output_time"] = fields.get(
            "last_output_time", sess.get("last_output_time", self.now())
        )
        for k, v in fields.items():
            sess[k] = v
        return self.store.put_session(sess)

    def inspect_output(self, text: str) -> list[str]:
        hits = []
        for name, pat in _POLICY_PATTERNS.items():
            if pat.search(text or ""):
                hits.append(name)
        return hits

    def snapshot(
        self,
        session_id: str,
        *,
        expected_branch: str = "",
        current_branch: str = "",
        current_head: str = "",
        process_alive: bool | None = None,
        output_text: str = "",
        changed_files: list[str] | None = None,
        max_changed_files: int = 80,
    ) -> MonitorSnapshot:
        sess = self.store.get_session(session_id) or {}
        now = self.now()
        started = float(sess.get("started_at") or now)
        last_out = float(sess.get("last_output_time") or sess.get("last_heartbeat") or started)
        last_cp = 0.0
        cps = self.store.checkpoints_for(session_id=session_id)
        if cps:
            last_cp = float(cps[-1].get("timestamp") or 0)
        phase = sess.get("phase") or (cps[-1].get("phase") if cps else "")
        status = sess.get("status") or SessionStatus.PENDING.value
        detections: list[str] = []
        warnings: list[str] = []

        if process_alive is False and status in (
            SessionStatus.RUNNING.value, SessionStatus.STARTING.value,
        ):
            detections.append("crashed_process")
            status = SessionStatus.CRASHED.value

        if status == SessionStatus.RUNNING.value and (now - last_out) > self.stall_timeout_sec:
            detections.append("stalled_session")
            status = SessionStatus.STALLED.value

        if expected_branch and current_branch and current_branch != expected_branch:
            detections.append("unexpected_branch_change")
            warnings.append(f"branch:{current_branch}!={expected_branch}")

        files = list(changed_files or sess.get("changed_files") or [])
        if len(files) > max_changed_files:
            detections.append("unbounded_file_changes")

        # no repository progress: running long with empty changes and old output
        if (
            status == SessionStatus.RUNNING.value
            and not files
            and (now - last_out) > min(self.stall_timeout_sec, 300)
        ):
            warnings.append("no_repository_progress")

        for d in self.inspect_output(output_text or sess.get("last_output") or ""):
            detections.append(d)

        # repeated command loop
        cmd = sess.get("active_command") or ""
        hist = sess.get("command_history") or []
        if cmd and len(hist) >= 3 and hist[-3:] == [cmd, cmd, cmd]:
            detections.append("repeated_command_loop")

        snap = MonitorSnapshot(
            session_id=session_id,
            status=status,
            phase=str(phase or ""),
            last_output_time=last_out,
            last_checkpoint_time=last_cp,
            process_healthy=process_alive is not False,
            head=current_head or sess.get("head") or "",
            branch=current_branch or sess.get("branch") or "",
            changed_files=files[:50],
            repeated_failures=int(sess.get("repeated_failures") or 0),
            blocked=bool(sess.get("blocked")),
            active_command=cmd,
            elapsed_sec=now - started,
            heartbeat_age_sec=now - float(sess.get("last_heartbeat") or started),
            detections=detections,
            warnings=warnings,
        )
        # persist status if changed
        if detections or status != sess.get("status"):
            sess["status"] = status
            sess["last_detections"] = detections
            self.store.put_session(sess)
        return snap
