"""M41 — Bounded read-only canary rollout (composes M39.3 + M40 + M39.5).

M41 is the operator-authorized canary layer. It NEVER grants ACTIVE, production,
write, or scope expansion, and it does NOT touch the M32 provider runtime's
prohibition of ExecutionMode.CANARY / ExecutionMode.ACTIVE (that gate is unchanged).
M41 canary is a distinct, bounded, read-only verification rollout for the single
LIVE-certified provider `github_meta`, governed by:

  * mandatory operator approval — a valid M39.3 operator canary approval record;
  * mandatory M40 LIVE_CERTIFIED evidence for the same provider;
  * mandatory automatic rollback — any M39.3 rollback trigger or M39.5 alert halts
    the rollout and rolls back;
  * mandatory kill switch — SAATHI_M39_KILL_SWITCH halts immediately;
  * bounded rollout (M39.3 1–5% ceiling), read-only, github_meta /user + /meta only.

Deny-by-default: without a valid approval record + live certification the verdict is
CANARY_NOT_ACTIVATED. Trading Guardian remains UNENGAGED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials import m39_3, m39_5
from saathi.credentials.m39 import (
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    AUTHORITIES,
    NON_PRODUCTION_BANNER,
    PROVIDER_ID,
    LiveKillSwitch,
    M39_ACK_TOKENS,
    _hmac,
    kill_switch_active,
    run_live_single_session,
)

SCHEMA_VERSION = "m41.canary_rollout.v1"
_FP_DOMAIN = b"saathi.m41.canary_rollout.domain.v1"

CANARY_ROLLOUT_MIN_PERCENT = m39_3.ROLLOUT_MIN_PERCENT   # 1
CANARY_ROLLOUT_MAX_PERCENT = m39_3.ROLLOUT_MAX_PERCENT   # 5 (hard ceiling)
DEFAULT_MAX_INCREMENTS = 3
DEFAULT_ERROR_BUDGET = 0   # zero tolerance for read-only canary: any error rolls back


class CanaryVerdict(str, Enum):
    CANARY_NOT_ACTIVATED = "CANARY_NOT_ACTIVATED"     # deny-by-default / unauthorized
    CANARY_BLOCKED = "CANARY_BLOCKED"                 # gate blocked (kill switch, etc.)
    CANARY_ROLLED_BACK = "CANARY_ROLLED_BACK"         # a trigger fired -> auto rollback
    CANARY_ACTIVE_BOUNDED = "CANARY_ACTIVE_BOUNDED"   # bounded read-only canary completed


class CanaryState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE_BOUNDED = "ACTIVE_BOUNDED"
    ROLLED_BACK = "ROLLED_BACK"
    COMPLETED = "COMPLETED"


@dataclass
class M41Config:
    mode: str = "live"  # "live" | "rehearsal"
    approval_record: Optional[dict[str, Any]] = None
    m40_cert_record: Optional[dict[str, Any]] = None
    rollout_percent: int = CANARY_ROLLOUT_MIN_PERCENT
    max_increments: int = DEFAULT_MAX_INCREMENTS
    error_budget: int = DEFAULT_ERROR_BUDGET
    # live execution reference (same reference-only contract as M40)
    secret_source_kind: str = ""
    secret_locator: str = ""
    env_var_name: str = ""
    expected_subject_fingerprint: str = ""
    acknowledgements: tuple[str, ...] = ()
    live_flag: bool = False
    environ: Optional[dict[str, str]] = None
    # rehearsal-only: force a 401 fault at this increment index to prove auto-rollback
    rehearsal_fault_at: int = -1


class M41Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ── authorization (deny-by-default) ──────────────────────────────────────────
def validate_canary_authorization(cfg: M41Config) -> dict[str, Any]:
    """Require a valid M39.3 approval record + M40 LIVE_CERTIFIED evidence."""
    blockers: list[str] = []

    approval = m39_3.validate_operator_approval_record(cfg.approval_record)
    if not approval["valid"]:
        blockers.append("operator_approval_invalid_or_absent")

    cert = cfg.m40_cert_record if isinstance(cfg.m40_cert_record, dict) else {}
    if cert.get("decision") != "LIVE_CERTIFIED" or not cert.get("live_certified"):
        blockers.append("m40_live_certification_required")
    if cert.get("provider") not in (None, PROVIDER_ID):
        blockers.append("provider_not_allowlisted")
    if cert.get("read_only") is False:
        blockers.append("provider_not_read_only")

    if not (CANARY_ROLLOUT_MIN_PERCENT <= cfg.rollout_percent <= CANARY_ROLLOUT_MAX_PERCENT):
        blockers.append("rollout_percent_out_of_bounds")
    if not (1 <= cfg.max_increments <= 10):
        blockers.append("invalid_max_increments")

    # approval-record scope must not widen beyond the read-only allowlist
    rec = cfg.approval_record or {}
    if rec.get("provider") not in (None, PROVIDER_ID):
        blockers.append("approval_provider_mismatch")
    for mth in (rec.get("methods") or []):
        if str(mth).upper() not in ALLOWED_METHODS:
            blockers.append("approval_method_not_allowlisted")
            break

    return {
        "schema": "m41.authorization.v1",
        "authorized": not blockers,
        "blockers": blockers,
        "approval_valid": approval["valid"],
        "m40_certified": cert.get("decision") == "LIVE_CERTIFIED",
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "contains_secret_values": False,
    }


# ── rollback triggers ────────────────────────────────────────────────────────
def evaluate_rollback(signals: dict[str, Any], *, environ: Optional[dict] = None) -> dict[str, Any]:
    """Any M39.5 alert or kill switch -> rollback. Mandatory, zero-tolerance."""
    alerts = m39_5.detect_alerts(signals)
    ks = kill_switch_active(environ)
    fired = list(alerts["fired"])
    if ks:
        fired.append({"id": "KILL", "name": "kill_switch_active", "severity": "SEV1"})
    should_rollback = bool(fired)
    return {
        "schema": "m41.rollback_eval.v1",
        "should_rollback": should_rollback,
        "triggers": fired,
        "highest_severity": "SEV1" if ks else alerts["highest_severity"],
        "contains_secret_values": False,
    }


# ── controller ───────────────────────────────────────────────────────────────
class CanaryController:
    """Bounded read-only canary state machine with mandatory auto-rollback + kill switch."""

    def __init__(self, cfg: M41Config, kill_switch: Optional[LiveKillSwitch] = None) -> None:
        self.cfg = cfg
        self.ks = kill_switch or LiveKillSwitch()
        self.state = CanaryState.NOT_STARTED
        self.increments: list[dict[str, Any]] = []
        self.errors = 0
        self.rollback_reason = ""

    def _run_read_only_call(self, index: int) -> dict[str, Any]:
        if self.cfg.mode == "rehearsal":
            transport = None
            if index == self.cfg.rehearsal_fault_at:
                from saathi.connectors.providers.external import testkit as _tk
                transport = _tk.make_transport(sender=_tk.fixture_sender(status=401))
            r = run_live_single_session(
                secret_source_kind="IN_MEMORY_TEST", secret_locator="m41/synth",
                acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True,
                transport=transport, session_id=f"m41_canary_{index}",
            )
        else:
            r = run_live_single_session(
                secret_source_kind=self.cfg.secret_source_kind,
                secret_locator=self.cfg.secret_locator,
                acknowledgements=self.cfg.acknowledgements,
                env_var_name=self.cfg.env_var_name, environ=self.cfg.environ,
                live_flag=self.cfg.live_flag,
                expected_subject_fingerprint=self.cfg.expected_subject_fingerprint,
                kill_switch=self.ks, session_id=f"m41_canary_{index}",
            )
        return r

    def run(self) -> dict[str, Any]:
        # kill switch pre-check
        if kill_switch_active(self.cfg.environ) or self.ks.is_tripped():
            self.state = CanaryState.ROLLED_BACK
            self.rollback_reason = "kill_switch_active"
            return self._body(CanaryVerdict.CANARY_BLOCKED)

        self.state = CanaryState.ACTIVE_BOUNDED
        for i in range(self.cfg.max_increments):
            r = self._run_read_only_call(i)
            ok = bool(r.get("ok"))
            reason = str(r.get("reason", ""))
            handle_closed = bool(r.get("handle_closed", True))
            if not ok:
                self.errors += 1
            self.increments.append({
                "index": i, "ok": ok, "reason": reason[:60],
                "handle_closed": handle_closed,
                "live_network": bool(r.get("live_network")),
            })
            # mandatory: evaluate rollback triggers after each increment
            signals = {
                "auth_denials": 1 if ("401" in reason or "403" in reason) else 0,
                "secret_resolution_failures": 1 if "secret" in reason and not ok else 0,
                "provider_failure_rate": 0.0 if ok else 1.0,
                "open_leases_after_cleanup": 0 if handle_closed else 1,
                "leak_findings": 0 if is_clean(r) else 1,
                "kill_switch_active": kill_switch_active(self.cfg.environ) or self.ks.is_tripped(),
            }
            ev = evaluate_rollback(signals, environ=self.cfg.environ)
            if ev["should_rollback"] or self.errors > self.cfg.error_budget:
                self.state = CanaryState.ROLLED_BACK
                self.rollback_reason = (
                    ev["triggers"][0]["name"] if ev["triggers"] else "error_budget_exceeded"
                )
                return self._body(CanaryVerdict.CANARY_ROLLED_BACK, last_eval=ev)

        self.state = CanaryState.COMPLETED
        return self._body(CanaryVerdict.CANARY_ACTIVE_BOUNDED)

    def _body(self, verdict: CanaryVerdict, *, last_eval: Optional[dict] = None) -> dict[str, Any]:
        all_handles_closed = all(x["handle_closed"] for x in self.increments)
        live = any(x["live_network"] for x in self.increments)
        return {
            "verdict": verdict.value,
            "state": self.state.value,
            "increments_run": len(self.increments),
            "errors": self.errors,
            "rollback_reason": self.rollback_reason,
            "all_handles_closed": all_handles_closed,
            "live_network": live,
            "last_rollback_eval": last_eval,
            "increments": self.increments,
        }


# ── top-level rollout ────────────────────────────────────────────────────────
def run_canary_rollout(cfg: Optional[M41Config] = None) -> dict[str, Any]:
    """Authorize, then run a bounded read-only canary under mandatory rollback."""
    cfg = cfg or M41Config()
    auth = validate_canary_authorization(cfg)
    if not auth["authorized"]:
        return _rollout_body(
            verdict=CanaryVerdict.CANARY_NOT_ACTIVATED.value,
            authorization=auth, controller_result=None, cfg=cfg)

    if kill_switch_active(cfg.environ):
        return _rollout_body(
            verdict=CanaryVerdict.CANARY_BLOCKED.value,
            authorization=auth, controller_result=None, cfg=cfg)

    controller = CanaryController(cfg)
    result = controller.run()
    return _rollout_body(
        verdict=result["verdict"], authorization=auth, controller_result=result, cfg=cfg)


def _valid_rehearsal_records() -> tuple[dict[str, Any], dict[str, Any]]:
    approval = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    approval.update(
        provider=PROVIDER_ID, endpoints=["user", "meta"], methods=["GET"],
        rollout_percent=1,
        explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS),
    )
    cert = {"decision": "LIVE_CERTIFIED", "live_certified": True,
            "provider": PROVIDER_ID, "read_only": True}
    return approval, cert


def run_canary_rehearsal(*, inject_rollback: bool = False,
                         fault_at: int = -1) -> dict[str, Any]:
    """Offline rehearsal of the canary state machine (authorized, fixtures, no live).

    inject_rollback=True trips the kill switch (pre-start block). fault_at forces a
    401 at that increment to prove auto-rollback DURING the bounded rollout.
    """
    approval, cert = _valid_rehearsal_records()
    environ = {"SAATHI_M39_KILL_SWITCH": "1"} if inject_rollback else {}
    cfg = M41Config(
        mode="rehearsal", approval_record=approval, m40_cert_record=cert,
        rollout_percent=1, max_increments=3, environ=environ, rehearsal_fault_at=fault_at,
    )
    body = run_canary_rollout(cfg)
    body["mode"] = "rehearsal"
    body["note"] = "SIMULATED_NOT_LIVE; proves authorization + bounded rollout + rollback wiring"
    return body


def _rollout_body(*, verdict: str, authorization: dict[str, Any],
                  controller_result: Optional[dict[str, Any]], cfg: M41Config) -> dict[str, Any]:
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M41",
        "verdict": verdict,
        "provider": PROVIDER_ID,
        "mode": "read_only_canary",
        "rollout_percent": cfg.rollout_percent,
        "rollout_ceiling_percent": CANARY_ROLLOUT_MAX_PERCENT,
        "authorization": authorization,
        "controller": controller_result,
        "rollback_triggers_armed": [t["id"] for t in m39_3.ROLLBACK_TRIGGERS],
        "kill_switch_env": "SAATHI_M39_KILL_SWITCH",
        "automatic_rollback": True,
        "grants_canary_execution": verdict == CanaryVerdict.CANARY_ACTIVE_BOUNDED.value,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "grants_rollout_full": False,
        "scope_expansion": "FORBIDDEN",
        "m32_canary_execution_mode": "PROHIBITION_UNCHANGED",
        "authorities": dict(AUTHORITIES),
        "banner": NON_PRODUCTION_BANNER,
        "trading_guardian": "UNENGAGED",
        "note": "M41 canary is bounded read-only verification, operator-authorized, "
                "auto-rollback + kill switch mandatory. Never ACTIVE/production/write. "
                "Does not modify the M32 ExecutionMode.CANARY prohibition.",
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({"verdict": verdict, "authorized": authorization["authorized"],
                    "rollout": cfg.rollout_percent}, sort_keys=True).encode(),
        length=24,
    )
    return body


def build_m41_evidence() -> dict[str, dict[str, Any]]:
    unauth = run_canary_rollout(M41Config())                 # deny-by-default
    rehearsal_ok = run_canary_rehearsal(inject_rollback=False)
    rehearsal_killswitch = run_canary_rehearsal(inject_rollback=True)
    rehearsal_rollback = run_canary_rehearsal(fault_at=1)     # 401 mid-rollout -> rollback
    return {
        "canary_not_activated_default": unauth,
        "canary_rehearsal_bounded": rehearsal_ok,
        "canary_rehearsal_killswitch_block": rehearsal_killswitch,
        "canary_rehearsal_auto_rollback": rehearsal_rollback,
        "summary": {
            "schema": "m41.summary.v1",
            "milestone": "M41",
            "default_verdict": unauth["verdict"],
            "rehearsal_verdict": rehearsal_ok["verdict"],
            "rehearsal_killswitch_verdict": rehearsal_killswitch["verdict"],
            "rehearsal_rollback_verdict": rehearsal_rollback["verdict"],
            "grants_active": False,
            "grants_production": False,
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m41_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m41_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m41 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
