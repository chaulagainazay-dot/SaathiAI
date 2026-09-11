"""FM-I2 — Bounded bridge from HarnessSessionController to real ExecutionGateway.

Uses only:
* isolated UniversalBoundary + ExecutionStore (temp SQLite)
* local family handlers (echo / ping / noop) — no shell, network, browser, FS
* deny / dry-run / approve / cancel seams already owned by ExecutionGateway

This is **not** a second gateway. It does not authorize; it only adapts
controller-built ToolIntent into ``ExecutionGateway.submit`` and maps
redacted ``ExecutionRecord`` results back to the harness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
import tempfile
import threading
import uuid

from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.execution.toolintent import ToolIntent


@dataclass
class GatewaySubmissionResult:
    """Normalized, redacted view of an ExecutionRecord for harness continuation."""

    ok: bool
    status: str
    summary: str
    execution_id: str = ""
    approval: str = "none"
    evidence_id: str = ""
    executed: bool = False
    path: str = "ExecutionGateway"
    raw_status: str = ""
    result: Mapping[str, Any] = field(default_factory=dict)

    def as_mapping(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "summary": self.summary,
            "execution_id": self.execution_id,
            "approval": self.approval,
            "evidence_id": self.evidence_id,
            "executed": self.executed,
            "path": self.path,
            "raw_status": self.raw_status,
            **dict(self.result),
        }


def build_isolated_execution_gateway(*, label: str = "fm-i2"):
    """Construct a process-local ExecutionGateway with isolated store + boundary.

    Does not touch the process-default singleton store used by production paths.
    """
    from saathi.execution.gateway import ExecutionGateway
    from saathi.execution.queue.memory import MemoryQueue
    from saathi.execution.store import ExecutionStore
    from saathi.execution.universal import UniversalBoundary

    tmp = Path(tempfile.mkdtemp(prefix=f"saathi-{label}-eg-"))
    db_path = tmp / "executions.db"
    store = ExecutionStore(db_path=db_path)
    # auto_integrations=False avoids pulling connector/MCP handlers into the proof.
    boundary = UniversalBoundary(store=store, auto_integrations=False)
    gateway = ExecutionGateway(MemoryQueue(), boundary=boundary)
    return gateway, store, tmp


class RealExecutionGatewayAdapter:
    """Adapter matching the FM-I1 double surface, backed by real ExecutionGateway.

    Side effects: only the safe ``local`` family handler (echo/ping/noop) or
    explicit denial/approval/cancel state transitions. Never shell/browser/net.
    """

    PATH = "ExecutionGateway"

    def __init__(
        self,
        gateway=None,
        *,
        isolated: bool = True,
        execute: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self.submitted: List[ToolIntent] = []
        self.cancelled_intent_ids: List[str] = []
        self.approved_execution_ids: List[str] = []
        self._results_by_idem: Dict[str, Mapping[str, Any]] = {}
        self._session_executions: Dict[str, List[str]] = {}
        self._records_by_execution: Dict[str, Any] = {}
        self.deny_all: bool = False
        self.execute: bool = execute
        self.raise_on_submit: bool = False
        self._tmp_dir: Optional[Path] = None

        if gateway is not None:
            self.gateway = gateway
            self._isolated = False
        elif isolated:
            self.gateway, self._store, self._tmp_dir = build_isolated_execution_gateway()
            self._isolated = True
        else:
            from saathi.execution.gateway import ExecutionGateway

            self.gateway = ExecutionGateway()
            self._isolated = False

    @property
    def is_real_gateway(self) -> bool:
        return True

    def submit(
        self,
        intent: ToolIntent,
        *,
        approval_id: str = "",
        execute: Optional[bool] = None,
    ) -> Mapping[str, Any]:
        """Submit immutable ToolIntent through real ExecutionGateway."""
        with self._lock:
            if self.raise_on_submit:
                raise RuntimeError("gateway adapter failure (injected)")
            errors = intent.validate()
            if errors:
                raise HarnessError(
                    HarnessErrorCode.MALFORMED_PROPOSAL,
                    f"invalid ToolIntent: {errors[0]}",
                    details={"errors": errors},
                )
            if self.deny_all:
                result = GatewaySubmissionResult(
                    ok=False,
                    status="denied",
                    summary="adapter deny_all",
                    path=self.PATH,
                    executed=False,
                ).as_mapping()
                return result

            # Idempotent client-side cache (EG also dedupes by key/digest)
            if (
                intent.idempotency_key
                and intent.idempotency_key in self._results_by_idem
                and not approval_id
            ):
                return dict(self._results_by_idem[intent.idempotency_key])

            do_execute = self.execute if execute is None else execute
            self.submitted.append(intent)
            rec = self.gateway.submit(
                intent,
                approval_id=approval_id or "",
                execute=do_execute,
            )
            mapped = self._map_record(rec, intent=intent)
            sid = str((intent.metadata or {}).get("session_id") or "")
            if sid and mapped.get("execution_id"):
                self._session_executions.setdefault(sid, []).append(
                    str(mapped["execution_id"])
                )
            if mapped.get("execution_id"):
                self._records_by_execution[str(mapped["execution_id"])] = rec
            # Cache terminal successes/denials only
            if mapped.get("status") not in ("approval_required", "approved_pending"):
                if intent.idempotency_key:
                    self._results_by_idem[intent.idempotency_key] = dict(mapped)
            return mapped

    def approve(
        self,
        execution_id: str,
        *,
        intent: ToolIntent,
        approval_id: str = "",
        execute: bool = True,
    ) -> Mapping[str, Any]:
        """Apply external approval to an APPROVAL_REQUIRED execution (controller only)."""
        with self._lock:
            aid = approval_id or f"apr-{uuid.uuid4().hex[:12]}"
            rec = self.gateway.approve_execution(
                execution_id,
                approval_id=aid,
                execute=execute,
                intent=intent,
            )
            self.approved_execution_ids.append(execution_id)
            mapped = self._map_record(rec, intent=intent)
            if intent.idempotency_key:
                self._results_by_idem[intent.idempotency_key] = dict(mapped)
            return mapped

    def cancel(self, execution_id: str, *, reason: str = "cancelled") -> None:
        """Cancel an in-flight or approval-required execution via real gateway."""
        with self._lock:
            self.cancelled_intent_ids.append(execution_id)
            if not execution_id:
                return
            try:
                self.gateway.cancel_execution(execution_id, reason=reason)
            except Exception:
                # Terminal / missing — fail soft; controller still fail-closes session
                pass

    def cancel_session(self, session_id: str, *, reason: str = "session_cancelled") -> List[str]:
        """Cancel all tracked executions for a harness session."""
        with self._lock:
            ids = list(self._session_executions.get(session_id, []))
        cancelled = []
        for eid in ids:
            self.cancel(eid, reason=reason)
            cancelled.append(eid)
        return cancelled

    def get_execution(self, execution_id: str):
        return self.gateway.get_execution(execution_id)

    def _map_record(self, rec: Any, *, intent: ToolIntent) -> Dict[str, Any]:
        status = str(getattr(rec, "status", "") or "")
        summary = str(getattr(rec, "result_summary", "") or "")
        execution_id = str(getattr(rec, "execution_id", "") or "")
        approval = str(getattr(rec, "approval", "") or "none")
        evidence_id = str(getattr(rec, "evidence_id", "") or "")

        # Terminal success only when handler ran and succeeded
        if status in ("succeeded", "success"):
            return GatewaySubmissionResult(
                ok=True,
                status="succeeded",
                summary=summary or f"local:{intent.operation}",
                execution_id=execution_id,
                approval=approval,
                evidence_id=evidence_id,
                executed=True,  # local no-op/echo ran inside EG — not external side effect
                path=self.PATH,
                raw_status=status,
                result={
                    "family": getattr(rec, "family", "local"),
                    "target": getattr(rec, "target", ""),
                },
            ).as_mapping()

        if status == "approval_required":
            return GatewaySubmissionResult(
                ok=False,
                status="approval_required",
                summary=summary or "awaiting approval",
                execution_id=execution_id,
                approval="required",
                evidence_id=evidence_id,
                executed=False,
                path=self.PATH,
                raw_status=status,
            ).as_mapping()

        if status == "approved" and not summary:
            # dry-run / execute=False stopped after auto-approve
            return GatewaySubmissionResult(
                ok=False,
                status="approved_pending",
                summary="approved but not executed (dry-run)",
                execution_id=execution_id,
                approval=approval,
                evidence_id=evidence_id,
                executed=False,
                path=self.PATH,
                raw_status=status,
            ).as_mapping()

        if status in ("denied", "failed", "cancelled", "expired"):
            return GatewaySubmissionResult(
                ok=False,
                status=status,
                summary=summary or status,
                execution_id=execution_id,
                approval=approval,
                evidence_id=evidence_id,
                executed=False,
                path=self.PATH,
                raw_status=status,
            ).as_mapping()

        return GatewaySubmissionResult(
            ok=False,
            status=status or "unknown",
            summary=summary or status,
            execution_id=execution_id,
            approval=approval,
            evidence_id=evidence_id,
            executed=False,
            path=self.PATH,
            raw_status=status,
        ).as_mapping()
