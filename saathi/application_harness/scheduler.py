"""M17.14 governed mission scheduler — deterministic, durable, restart-safe.

The scheduler sits ABOVE the MissionEngine. It NEVER executes a pipeline, harness,
adapter, shell, tool, or external service. Its only power is to create/claim a valid
mission OCCURRENCE at a due time and DELEGATE it to the existing MissionEngine:

    Scheduler → Mission instance → MissionEngine → PipelineRunner →
    run_harness_action → Adapter → independent verification → durable ledger

Everything is fail-closed: an invalid schedule, owner, template, parameter set, or
approval state records a safe failure and never executes. Ownership is preserved end
to end; scheduling never implies approval (an approval-required mission stops at
`approval_required`). All state lives in the SAME durable ledger DB (additive
`mission_schedule` + `mission_occurrence` tables); there is NO second scheduler DB,
job runner, or execution engine.

Determinism: the clock is injectable everywhere (`now`); due-time math is pure and
timezone-aware (UTC internally, wall-clock computed in the schedule's IANA zone via
`zoneinfo`, so DST is handled by the library — a daily 06:00 job stays at 06:00
local across a DST change, and its UTC epoch shifts by the offset). No randomness,
no real sleeps.

Idempotency + concurrency: each due time yields exactly ONE occurrence
(`UNIQUE(dedup_key)` = `schedule_id:normalized_due_at:version`), and each occurrence
yields at most ONE mission (a DETERMINISTIC mission id derived from the occurrence,
so a crash-after-create re-attempt reconciles the existing mission instead of making
a second one). Lease-based claiming lets concurrent sweeps run without duplicate
work; an active lease is never stealable; an expired lease is recovered on restart.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as _tz
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from saathi.application_harness import run_ledger as L
from saathi.application_harness.mission import MissionEngine, validate_params

_MIN_INTERVAL_SEC = 1.0
_MAX_CATCHUP = 50                 # bound per-sweep occurrence generation (no storms)
_DEFAULT_LEASE_SEC = 120.0


# ── deterministic due-time math (pure, timezone-aware, DST-correct) ─────────
def validate_timezone(tz_name: str) -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, Exception):
        return None


def _parse_hhmm(s) -> Optional[tuple]:
    try:
        hh, mm = str(s).split(":")
        h, m = int(hh), int(mm)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:
        return None
    return None


def validate_expression(schedule_type: str, expression: dict) -> dict:
    """Strictly validate a schedule expression for its type. Returns
    {"ok": True} or {"ok": False, "reason": ...}. Fail closed."""
    expression = expression or {}
    if schedule_type == "one_time":
        try:
            ra = float(expression.get("run_at"))
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_run_at"}
        if ra <= 0:
            return {"ok": False, "reason": "invalid_run_at"}
        return {"ok": True}
    if schedule_type == "interval":
        try:
            iv = float(expression.get("interval_sec"))
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_interval"}
        if iv < _MIN_INTERVAL_SEC:
            return {"ok": False, "reason": "interval_too_small"}
        return {"ok": True}
    if schedule_type == "daily":
        if _parse_hhmm(expression.get("time")) is None:
            return {"ok": False, "reason": "invalid_time"}
        return {"ok": True}
    if schedule_type == "weekly":
        if _parse_hhmm(expression.get("time")) is None:
            return {"ok": False, "reason": "invalid_time"}
        wd = expression.get("weekday")
        if not isinstance(wd, int) or not (0 <= wd <= 6):
            return {"ok": False, "reason": "invalid_weekday"}
        return {"ok": True}
    return {"ok": False, "reason": "unknown_schedule_type"}


def compute_next_due(schedule_type: str, expression: dict, tz_name: str,
                     after_epoch: float) -> Optional[float]:
    """First due time STRICTLY AFTER `after_epoch` (UTC epoch seconds). Returns None
    for a one_time schedule already past its run_at. Deterministic + tz-aware."""
    expression = expression or {}
    if schedule_type == "one_time":
        ra = float(expression["run_at"])
        return ra if ra > after_epoch else None
    if schedule_type == "interval":
        iv = float(expression["interval_sec"])
        # advance from the anchor (run_at or 0) so the grid is stable + deterministic
        anchor = float(expression.get("anchor", 0.0))
        if after_epoch < anchor:
            return anchor
        steps = int((after_epoch - anchor) // iv) + 1
        return anchor + steps * iv
    tz = validate_timezone(tz_name) or _tz.utc
    h, m = _parse_hhmm(expression["time"])
    after_dt = datetime.fromtimestamp(after_epoch, tz)
    if schedule_type == "daily":
        cand = after_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand.timestamp() <= after_epoch:
            cand = (after_dt + timedelta(days=1)).replace(hour=h, minute=m,
                                                          second=0, microsecond=0)
        return cand.timestamp()
    if schedule_type == "weekly":
        wd = int(expression["weekday"])
        for add in range(0, 8):
            d = after_dt + timedelta(days=add)
            if d.weekday() != wd:
                continue
            cand = d.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand.timestamp() > after_epoch:
                return cand.timestamp()
        return None
    return None


def _occurrence_id(dedup_key: str) -> str:
    return "occ_" + hashlib.sha256(dedup_key.encode()).hexdigest()[:20]


def _dedup_key(schedule_id: str, due_at: float, version: int) -> str:
    return f"{schedule_id}:{int(due_at)}:{int(version)}"


def _mission_id_for(occurrence_id: str) -> str:
    # DETERMINISTIC: a crash-after-create re-attempt maps to the SAME mission id,
    # so create_mission returns a duplicate and no second mission is made.
    return "ms_" + hashlib.sha256(occurrence_id.encode()).hexdigest()[:20]


@dataclass(frozen=True)
class _Clock:
    """Injectable clock. `at` fixes time for deterministic tests."""
    at: Optional[float] = None

    def now(self) -> float:
        return self.at if self.at is not None else L._now()


class MissionScheduler:
    """Bounded coordinator. Does not execute anything itself — it creates/claims
    occurrences and hands each to the MissionEngine."""

    def __init__(self, *, ledger: L.RunLedger | None = None,
                 engine: MissionEngine | None = None,
                 lease_sec: float = _DEFAULT_LEASE_SEC):
        self.ledger = ledger or L.default_ledger()
        self.engine = engine or MissionEngine(ledger=self.ledger)
        self.lease_sec = lease_sec

    # ── schedule definition (fail-closed validation) ───────────────────────
    def create_schedule(self, *, owner, mission_template_id, schedule_type,
                        timezone="UTC", expression=None, params=None,
                        description="", retry_policy="default", schedule_id="",
                        now=None) -> dict:
        now = now if now is not None else L._now()
        expression = expression or {}
        params = params or {}
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        if schedule_type not in L.SCHEDULE_TYPES:
            return {"ok": False, "reason": "unknown_schedule_type"}
        if validate_timezone(timezone) is None:
            return {"ok": False, "reason": "invalid_timezone"}
        ev = validate_expression(schedule_type, expression)
        if not ev["ok"]:
            return {"ok": False, "reason": ev["reason"]}
        tmpl = self.engine.templates.get(mission_template_id)
        if tmpl is None:
            return {"ok": False, "reason": "unknown_template"}
        pv = validate_params(tmpl.parameters, params)
        if not pv["ok"]:
            return {"ok": False, "reason": "invalid_parameters", "errors": pv["errors"]}
        first_due = compute_next_due(schedule_type, expression, timezone, now - 1e-6)
        if first_due is None:
            return {"ok": False, "reason": "no_future_due"}
        sid = schedule_id or ("sch_" + uuid.uuid4().hex[:16])
        created = self.ledger.create_schedule(
            sid, owner=owner, mission_template_id=mission_template_id,
            schedule_type=schedule_type, timezone=timezone, expression=expression,
            params=pv["values"], description=description, retry_policy=retry_policy,
            next_due_at=first_due, now=now)
        if not created.get("created"):
            return {"ok": False, "schedule_id": sid, "reason": created.get("reason")}
        return {"ok": True, "schedule_id": sid, "next_due_at": first_due}

    def pause(self, schedule_id, *, owner, now=None) -> dict:
        return self._status(schedule_id, owner, L.SCHEDULE_PAUSED, now)

    def resume(self, schedule_id, *, owner, now=None) -> dict:
        return self._status(schedule_id, owner, L.SCHEDULE_ACTIVE, now)

    def disable(self, schedule_id, *, owner, now=None) -> dict:
        return self._status(schedule_id, owner, L.SCHEDULE_DISABLED, now)

    def _status(self, schedule_id, owner, to_status, now) -> dict:
        s = self.ledger.get_schedule(schedule_id)
        if s is None:
            return {"ok": False, "reason": "unknown_schedule"}
        if s["owner"] != owner:
            return {"ok": False, "reason": "owner_mismatch"}
        return self.ledger.set_schedule_status(schedule_id, to_status=to_status, now=now)

    # ── occurrence generation (idempotent, bounded) ────────────────────────
    def create_due_occurrences(self, *, now=None) -> dict:
        now = now if now is not None else L._now()
        created = []
        for s in self.ledger.due_schedules(now=now):
            created.extend(self._materialize(s, now))
        return {"created": created, "count": len(created)}

    def _materialize(self, s, now) -> list:
        sid, stype = s["schedule_id"], s["schedule_type"]
        expr, version = s["expression"], s["version"]
        due = s["next_due_at"]
        made, last_due, last_occ = [], None, None
        guard = 0
        while due and due <= now and guard < _MAX_CATCHUP:
            guard += 1
            key = _dedup_key(sid, due, version)
            oid = _occurrence_id(key)
            r = self.ledger.create_occurrence(oid, schedule_id=sid, owner=s["owner"],
                                               due_at=due, dedup_key=key, now=now)
            if r.get("created"):
                made.append(oid)
            last_due, last_occ = due, oid
            if stype == "one_time":
                due = None
                break
            due = compute_next_due(stype, expr, s["timezone"], due)
        if stype == "one_time" and last_occ is not None:
            self.ledger.update_schedule_due(sid, next_due_at=0.0, last_due_at=last_due,
                                            last_occurrence_id=last_occ, now=now)
            self.ledger.set_schedule_status(sid, to_status=L.SCHEDULE_COMPLETED, now=now)
        elif last_due is not None:
            self.ledger.update_schedule_due(sid, next_due_at=(due or 0.0),
                                            last_due_at=last_due,
                                            last_occurrence_id=last_occ, now=now)
        return made

    # ── dispatch: delegate to the MissionEngine ONLY ───────────────────────
    def dispatch_occurrence(self, occurrence_id, *, now=None, worker="scheduler",
                            graph_recovery=False) -> dict:
        now = now if now is not None else L._now()
        occ = self.ledger.inspect_occurrence(occurrence_id)
        if occ is None:
            return {"ok": False, "reason": "unknown_occurrence"}
        s = self.ledger.get_schedule(occ["schedule_id"])
        # 1. a paused/disabled/invalid schedule must NOT run its occurrences. A
        # `completed` one_time schedule is the normal happy path (its occurrence was
        # validly generated before completion), so only the deactivated states block.
        if s is None:
            return self._terminal(occurrence_id, L.OCC_FAILED, "schedule_missing", now=now)
        if s["status"] in (L.SCHEDULE_PAUSED, L.SCHEDULE_DISABLED, L.SCHEDULE_INVALID):
            return self._terminal(occurrence_id, L.OCC_CANCELLED, "schedule_inactive",
                                  detail=s["status"], now=now)
        # 2. owner consistency BEFORE the engine is touched
        if s["owner"] != occ["owner"]:
            return self._terminal(occurrence_id, L.OCC_FAILED, "owner_mismatch", now=now)
        owner = occ["owner"]
        # 3. template must still exist
        tmpl = self.engine.templates.get(s["mission_template_id"])
        if tmpl is None:
            return self._terminal(occurrence_id, L.OCC_FAILED, "invalid_template", now=now)
        # 4. parameters valid (existing MissionEngine validation)
        pv = validate_params(tmpl.parameters, s["params"])
        if not pv["ok"]:
            return self._terminal(occurrence_id, L.OCC_FAILED, "invalid_parameters",
                                  detail=",".join(pv["errors"])[:120], now=now)
        # 5. atomic claim
        if not self.ledger.claim_occurrence(occurrence_id, worker=worker, now=now,
                                             lease_sec=self.lease_sec):
            return {"ok": False, "reason": "claim_lost"}
        try:
            # 6. create ONE mission idempotently (deterministic id → crash-safe)
            mid = _mission_id_for(occurrence_id)
            res = self.engine.create(s["mission_template_id"], owner=owner,
                                     params=s["params"], mission_id=mid,
                                     correlation_id=occurrence_id)
            if not res.get("ok") and res.get("reason") != "duplicate_mission_id":
                return self._terminal(occurrence_id, L.OCC_FAILED,
                                      res.get("reason", "mission_create_failed"), now=now)
            # 7-8. link + drive through the MissionEngine ONLY (never the pipeline/adapter direct)
            self.ledger.link_occurrence_mission(occurrence_id, mission_id=mid, now=now)
            self.engine.launch(mid, owner=owner, session_id=f"scheduler:{occurrence_id}")
            # 9. observe the AUTHORITATIVE mission result
            m = self.engine.inspect(mid, owner=owner)
            return self._finalize_from_mission(occurrence_id, m, now=now,
                                               graph_recovery=graph_recovery)
        except Exception as e:                     # infrastructure failure → retry
            self.ledger.occurrence_retry(occurrence_id,
                                         reason=f"dispatch:{type(e).__name__}", now=now)
            return {"ok": False, "state": L.OCC_RETRY_WAIT, "reason": str(e)[:120]}

    _MISSION_TO_OCC = {
        L.MISSION_COMPLETED: L.OCC_SUCCEEDED, L.MISSION_FAILED: L.OCC_FAILED,
        L.MISSION_BLOCKED: L.OCC_BLOCKED, L.MISSION_CANCELLED: L.OCC_CANCELLED,
        L.MISSION_APPROVAL_REQUIRED: L.OCC_APPROVAL_REQUIRED,
    }

    def _graph_retryable(self, pipeline_id) -> bool:
        """M17.17: does this graph pipeline carry an OPEN, allowlisted-transient
        recovery record with retries remaining? (observed via the existing recovery
        interface — the scheduler never computes graph-ready/checkpoint logic)."""
        from saathi.application_harness.pipeline_recovery import is_retryable
        rec = self.ledger.get_recovery(pipeline_id)
        if not rec or rec["state"] in L.RECOVERY_TERMINAL:
            return False
        return (is_retryable(rec["failure_category"])
                and rec["attempt"] < rec["max_attempts"])

    def _finalize_from_mission(self, occurrence_id, mission, *, now=None,
                               graph_recovery=False) -> dict:
        if mission is None:                        # should not happen → retry
            self.ledger.occurrence_retry(occurrence_id, reason="mission_missing", now=now)
            return {"ok": False, "state": L.OCC_RETRY_WAIT}
        st = mission["state"]
        fcode = mission.get("failure_code", "") or ""
        # M17.17: a fail-closed graph awaiting approval propagates approval_required
        if st == L.MISSION_BLOCKED and fcode == "GRAPH_APPROVAL_REQUIRED":
            occ_state = L.OCC_APPROVAL_REQUIRED
        else:
            occ_state = self._MISSION_TO_OCC.get(st)
        if occ_state is None:                      # mission not resolved (crash) → retry
            self.ledger.occurrence_retry(occurrence_id,
                                         reason=f"mission_unresolved:{st}", now=now)
            return {"ok": False, "state": L.OCC_RETRY_WAIT}
        # M17.17: defer terminal failure when the graph left a RETRYABLE recovery
        # record, so the scheduled-graph recovery coordinator can resume it. A
        # non-retryable graph failure still goes terminal at once (no relaunch storm).
        if graph_recovery and occ_state == L.OCC_FAILED:
            pid = mission.get("last_pipeline_id") or ""
            if pid and self._graph_retryable(pid):
                self.ledger.occurrence_retry(occurrence_id, reason="graph_retryable",
                                             now=now)
                return {"ok": False, "state": L.OCC_RETRY_WAIT, "recoverable": True,
                        "mission_id": mission["mission_id"], "pipeline_id": pid}
        cat = "" if occ_state == L.OCC_SUCCEEDED else st
        summary = fcode if occ_state != L.OCC_SUCCEEDED else ""
        run_id = str(mission["run_count"]) if mission.get("run_count") else ""
        self.ledger.finish_occurrence(occurrence_id, state=occ_state,
                                      mission_run_id=run_id, failure_category=cat,
                                      failure_summary=summary, now=now)
        return {"ok": occ_state == L.OCC_SUCCEEDED, "state": occ_state,
                "mission_id": mission["mission_id"], "mission_state": st}

    def settle_occurrence_from_mission(self, occurrence_id, mission, *, now=None,
                                       graph_recovery=False) -> dict:
        """Public entry for the M17.17 coordinator to settle an occurrence from an
        authoritative mission record, reusing the SAME honest mapping (approval →
        approval_required; retryable graph failure → deferred retry_wait)."""
        return self._finalize_from_mission(occurrence_id, mission, now=now,
                                           graph_recovery=graph_recovery)

    def _terminal(self, occurrence_id, state, category, *, detail="", now=None) -> dict:
        self.ledger.finish_occurrence(occurrence_id, state=state,
                                      failure_category=category,
                                      failure_summary=detail, now=now)
        return {"ok": False, "state": state, "reason": category}

    # ── reconciliation (restart-safe; never duplicates work) ───────────────
    def reconcile(self, *, now=None) -> dict:
        now = now if now is not None else L._now()
        reconciled, requeued = [], []
        for occ in self.ledger.reclaim_stale_occurrences(now=now, lease_sec=self.lease_sec):
            oid = occ["occurrence_id"]
            mid = occ["mission_id"]
            if not mid:                            # crashed before mission → requeue
                self.ledger.requeue_occurrence(oid, now=now)
                requeued.append(oid); continue
            m = self.engine.inspect(mid)           # the mission already exists
            if m is None:
                self.ledger.requeue_occurrence(oid, now=now); requeued.append(oid); continue
            if m["state"] in L.MISSION_TERMINAL or m["state"] == L.MISSION_APPROVAL_REQUIRED:
                self._finalize_from_mission(oid, m, now=now)
                reconciled.append(oid)
            else:                                  # mission mid-flight → re-drive safely
                self.engine.launch(mid, owner=m["owner"],
                                   session_id=f"reconcile:{oid}")
                self._finalize_from_mission(oid, self.engine.inspect(mid), now=now)
                reconciled.append(oid)
        return {"reconciled": reconciled, "requeued": requeued}

    # ── one deterministic sweep ────────────────────────────────────────────
    def sweep(self, *, now=None, worker="scheduler", limit=100) -> dict:
        now = now if now is not None else L._now()
        recon = self.reconcile(now=now)
        gen = self.create_due_occurrences(now=now)
        dispatched = []
        for occ in self.ledger.pending_due_occurrences(now=now, limit=limit):
            r = self.dispatch_occurrence(occ["occurrence_id"], now=now, worker=worker)
            dispatched.append({"occurrence_id": occ["occurrence_id"],
                               "state": r.get("state"), "ok": r.get("ok")})
        return {"reconciled": recon, "generated": gen["created"],
                "dispatched": dispatched, "swept_at": now}

    # ── owner-safe health ──────────────────────────────────────────────────
    def health(self, owner: str | None = None, *, now=None) -> dict:
        now = now if now is not None else L._now()
        return {"schedules": self.ledger.schedule_health(owner),
                "occurrences": self.ledger.occurrence_health(owner, now=now),
                "generated_at": now}


_default: MissionScheduler | None = None


def default_scheduler() -> MissionScheduler:
    global _default
    if _default is None:
        _default = MissionScheduler()
    return _default
