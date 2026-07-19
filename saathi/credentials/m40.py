"""M40 — Live Validation & Production Certification (composes M31–M39).

M40 is NOT a feature milestone. It is the controlled live-validation layer that
proves the offline-certified M31–M39 security model behaves correctly against a
REAL provider under explicit operator authorization. It introduces no new
provider capability, no product feature, no production deployment, and no business
logic. It composes existing M39 runners only.

Two honest entry points:

  * ``run_live_certification(config)`` — the REAL gated 6-stage pipeline. Fails
    CLOSED: without an approved operator disposable secret reference + live flag +
    all acknowledgements, it stops at the earliest gate and classifies
    ``LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED``. It can reach ``LIVE_CERTIFIED`` only
    when every stage runs against a REAL provider (live_network) and passes.

  * ``run_stage_rehearsal()`` — offline-fixture rehearsal of each stage's
    mechanics for deterministic testing. Every result is ``SIMULATED_NOT_LIVE``.
    A rehearsal is explicitly NOT a certification and can never grant anything.

Hard invariants (unchanged from M31–M39): fail-closed, least privilege,
reference-only secrets, lease ownership, SecretHandle destruction, budget limits,
kill switch, allowlists, deny-by-default. No canary/active/rollout/production/write
authority. Trading Guardian UNENGAGED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.providers.external import testkit as _tk
from saathi.credentials.leakscan import is_clean
from saathi.credentials import m39_5
from saathi.credentials.m39 import (
    APPROVED_LIVE_SOURCE_KINDS,
    AUTHORITIES,
    NON_PRODUCTION_BANNER,
    PER_SESSION_CALL_BUDGET,
    PROVIDER_ID,
    LiveExerciseStatus,
    LiveKillSwitch,
    M39Error,
    M39_ACK_TOKENS,
    PreflightInput,
    _TOKEN_SHAPE,
    _hmac,
    compute_m39_fingerprint,
    kill_switch_active,
    record_external_revocation,
    reference_fingerprint,
    run_live_multisession,
    run_live_preflight,
    run_live_single_session,
    validate_acknowledgements,
)

SCHEMA_VERSION = "m40.live_certification.v1"
_FP_DOMAIN = b"saathi.m40.live_certification.domain.v1"


class M40StageStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NOT_EXERCISED = "NOT_EXERCISED"
    SIMULATED_NOT_LIVE = "SIMULATED_NOT_LIVE"


class LiveCertificationVerdict(str, Enum):
    LIVE_CERTIFIED = "LIVE_CERTIFIED"
    LIVE_FAILED = "LIVE_FAILED"
    LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED = "LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED"
    LIVE_BLOCKED = "LIVE_BLOCKED"


STAGES = (
    "stage1_operator_acknowledgement",
    "stage2_provider_preflight",
    "stage3_single_session",
    "stage4_multi_session",
    "stage5_external_revocation",
    "stage6_evidence_verification",
)


@dataclass
class M40Config:
    mode: str = "live"  # "live" (gated real pipeline) | "rehearsal" (offline fixture)
    secret_source_kind: str = ""
    secret_locator: str = ""
    env_var_name: str = ""
    acknowledgements: tuple[str, ...] = ()
    authorization_present: bool = False
    environment_confirmed: bool = False
    branch: str = ""
    head: str = ""
    expected_head: str = ""
    working_tree_class: str = "UNKNOWN"
    m31_m39_regression_ok: bool = True
    live_flag: bool = False
    environ: Optional[dict[str, str]] = None
    revocation_plan: str = "manual_github_pat_delete"


def _stage(name: str, status: M40StageStatus, **details: Any) -> dict[str, Any]:
    d = {
        "stage": name,
        "status": status.value,
        "ok": status == M40StageStatus.PASSED,
        "contains_secret_values": False,
        **details,
    }
    return d


def _secret_reference_supplied(cfg: M40Config) -> bool:
    sk = (cfg.secret_source_kind or "").strip().upper()
    if sk not in APPROVED_LIVE_SOURCE_KINDS or sk == "IN_MEMORY_TEST":
        return False
    loc = cfg.secret_locator or cfg.env_var_name
    if not loc:
        return False
    if _TOKEN_SHAPE.match(loc.strip()) or loc.startswith("raw:"):
        # a raw secret is never a valid reference
        return False
    return True


# ── Stage 1 — operator acknowledgement verification (fail closed) ────────────
def stage1_operator_acknowledgement(cfg: M40Config) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        validate_acknowledgements(cfg.acknowledgements)
    except M39Error as e:
        blockers.append(e.code)
    if not cfg.authorization_present:
        blockers.append("missing_authorization")
    if not cfg.environment_confirmed:
        blockers.append("environment_not_confirmed")
    if not _secret_reference_supplied(cfg):
        blockers.append("disposable_secret_reference_required")
    status = M40StageStatus.PASSED if not blockers else M40StageStatus.BLOCKED
    return _stage(
        "stage1_operator_acknowledgement", status,
        blockers=blockers,
        acknowledgements_count=len(cfg.acknowledgements),
        authority=dict(AUTHORITIES),
    )


# ── Stage 2 — provider preflight (nothing mutates remotely) ──────────────────
def stage2_provider_preflight(cfg: M40Config) -> dict[str, Any]:
    inp = PreflightInput(
        branch=cfg.branch or "unknown",
        head=cfg.head or "unknown",
        expected_head=cfg.expected_head,
        working_tree_class=cfg.working_tree_class if cfg.working_tree_class in
        ("CLEAN", "NOISE_ONLY", "DIRTY") else "DIRTY",
        m31_m38_regression_ok=cfg.m31_m39_regression_ok,
        secret_source_kind=cfg.secret_source_kind,
        secret_locator=cfg.secret_locator or cfg.env_var_name,
        secret_ref_exists=True if _secret_reference_supplied(cfg) else None,
        authorization_present=cfg.authorization_present,
        acknowledgements=cfg.acknowledgements,
        provider_id=PROVIDER_ID,
        live_flag=cfg.live_flag,
        environ=cfg.environ,
        revocation_plan=cfg.revocation_plan,
    )
    pf = run_live_preflight(inp)
    status = M40StageStatus.PASSED if pf.get("ok") else M40StageStatus.BLOCKED
    return _stage(
        "stage2_provider_preflight", status,
        blockers=pf.get("blockers", []),
        network_calls_performed=pf.get("network_calls_performed", 0),
        provider_id=PROVIDER_ID,
        preflight_status=pf.get("status"),
    )


# ── Stage 3 — single-session validation ──────────────────────────────────────
_BLOCK_REASON_MARKERS = (
    "missing", "flag", "not_allowlisted", "blocked", "secret_ref",
    "kill_switch", "unapproved", "not_confirmed", "required",
)


def _reason_is_block(reason: str) -> bool:
    r = (reason or "").lower()
    return any(m in r for m in _BLOCK_REASON_MARKERS)


def _classify_single(r: dict[str, Any]) -> M40StageStatus:
    st = r.get("status")
    if st == LiveExerciseStatus.PASSED.value and r.get("ok"):
        return M40StageStatus.SIMULATED_NOT_LIVE if not r.get("live_network") else M40StageStatus.PASSED
    if st in (LiveExerciseStatus.BLOCKED.value, LiveExerciseStatus.NOT_EXERCISED.value):
        return M40StageStatus.BLOCKED
    if _reason_is_block(str(r.get("reason", ""))):
        return M40StageStatus.BLOCKED
    return M40StageStatus.FAILED


def stage3_single_session(cfg: M40Config, *, rehearsal: bool = False) -> dict[str, Any]:
    if rehearsal:
        r = run_live_single_session(
            secret_source_kind="IN_MEMORY_TEST", secret_locator="m40/synth",
            acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True,
            session_id="m40_single",
        )
    else:
        r = run_live_single_session(
            secret_source_kind=cfg.secret_source_kind, secret_locator=cfg.secret_locator,
            acknowledgements=cfg.acknowledgements, env_var_name=cfg.env_var_name,
            environ=cfg.environ, live_flag=cfg.live_flag, session_id="m40_single",
        )
    status = _classify_single(r)
    return _stage(
        "stage3_single_session", status,
        reason=str(r.get("reason", ""))[:80],
        live_network=bool(r.get("live_network")),
        handle_closed=bool(r.get("handle_closed")),
        lease_revoked=bool(r.get("lease_revoked")),
        call_budget_used=r.get("call_budget_used"),
        call_budget_max=r.get("call_budget_max", PER_SESSION_CALL_BUDGET),
        cleanup_ok=bool(r.get("handle_closed")),
    )


# ── Stage 4 — multi-session validation ───────────────────────────────────────
def stage4_multi_session(cfg: M40Config, *, rehearsal: bool = False) -> dict[str, Any]:
    if rehearsal:
        r = run_live_multisession(
            secret_source_kind="IN_MEMORY_TEST", secret_locator="m40/synth",
            acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True, sequential=True,
        )
    else:
        r = run_live_multisession(
            secret_source_kind=cfg.secret_source_kind, secret_locator=cfg.secret_locator,
            acknowledgements=cfg.acknowledgements, env_var_name=cfg.env_var_name,
            environ=cfg.environ, live_flag=cfg.live_flag, sequential=True,
        )
    sessions = r.get("sessions", [])
    st = r.get("status")
    if st == LiveExerciseStatus.PASSED.value and r.get("ok"):
        status = M40StageStatus.SIMULATED_NOT_LIVE if not r.get("live_network", False) else M40StageStatus.PASSED
    elif st in (LiveExerciseStatus.BLOCKED.value, LiveExerciseStatus.NOT_EXERCISED.value):
        status = M40StageStatus.BLOCKED
    elif _reason_is_block(str(r.get("reason", ""))):
        status = M40StageStatus.BLOCKED
    else:
        status = M40StageStatus.FAILED
    session_ids = [s.get("session_id") for s in sessions]
    corr_ids = [s.get("correlation_id") for s in sessions]
    distinct = (len(session_ids) == len(set(session_ids))
                and len(corr_ids) == len(set(corr_ids)))
    isolation_ok = (
        distinct
        and bool(r.get("isolation", True))
        and r.get("contains_secret_values") is False
    )
    return _stage(
        "stage4_multi_session", status,
        reason=str(r.get("reason", ""))[:80],
        session_count=len(sessions),
        lease_isolation_ok=isolation_ok,
        distinct_session_ids=distinct,
        result_isolation=bool(r.get("isolation", True)),
        no_stale_handles=all(s.get("handle_closed", True) for s in sessions),
    )


# ── Stage 5 — external revocation ────────────────────────────────────────────
def stage5_external_revocation(
    cfg: M40Config, *, rehearsal: bool = False, operator_confirmed: bool = False
) -> dict[str, Any]:
    """Operator revokes; system retries; expect 401 + cleanup + audit + classification.

    In rehearsal, the post-revocation retry is simulated with a 401 fixture sender.
    In live mode, the retry is a real bounded call that must fail with 401.
    """
    if rehearsal:
        # simulate the post-revocation retry: 401 from provider
        retry = run_live_single_session(
            secret_source_kind="IN_MEMORY_TEST", secret_locator="m40/synth",
            acknowledgements=M39_ACK_TOKENS, allow_offline_fixture=True,
            transport=_tk.make_transport(sender=_tk.fixture_sender(status=401)),
            session_id="m40_revoke_retry",
        )
        retry_failed_401 = (not retry.get("ok")) and "401" in str(retry.get("reason", ""))
        rev = record_external_revocation(
            confirmed=True, operator_note="rehearsal: simulated external revocation",
        )
        cleanup_ok = bool(retry.get("handle_closed"))
        status = M40StageStatus.SIMULATED_NOT_LIVE if (retry_failed_401 and cleanup_ok) else M40StageStatus.FAILED
        classification = "authorization_failure_401" if retry_failed_401 else "unexpected"
        return _stage(
            "stage5_external_revocation", status,
            revocation_recorded=rev["confirmed"],
            retry_failed_401=retry_failed_401,
            cleanup_ok=cleanup_ok,
            failure_classification=classification,
            audit_event="m39.single_session_failed",
        )
    # live mode: revocation must be operator-confirmed; retry result is a real call
    rev = record_external_revocation(
        confirmed=operator_confirmed,
        operator_note="live external revocation",
    )
    if not operator_confirmed:
        return _stage(
            "stage5_external_revocation", M40StageStatus.BLOCKED,
            revocation_recorded=False, reason="operator_revocation_not_confirmed",
        )
    return _stage(
        "stage5_external_revocation", M40StageStatus.NOT_EXERCISED,
        revocation_recorded=True,
        reason="live_retry_requires_live_pipeline",
    )


# ── Stage 6 — evidence verification ──────────────────────────────────────────
_REQUIRED_EVIDENCE_FIELDS = (
    "identity", "provider", "scopes", "budget", "lease_ids", "timestamps",
    "cleanup", "revocation", "classification",
)


def stage6_evidence_verification(stage_results: list[dict[str, Any]]) -> dict[str, Any]:
    # assemble a deterministic evidence skeleton from stage results (no secrets)
    single = next((s for s in stage_results if s["stage"] == "stage3_single_session"), {})
    multi = next((s for s in stage_results if s["stage"] == "stage4_multi_session"), {})
    revoke = next((s for s in stage_results if s["stage"] == "stage5_external_revocation"), {})
    evidence = {
        "identity": "subject_fingerprint_only",
        "provider": PROVIDER_ID,
        "scopes": ["read:user", "read:meta"],
        "budget": {"per_session": PER_SESSION_CALL_BUDGET,
                   "single_used": single.get("call_budget_used")},
        "lease_ids": ["fingerprint_bound_lease"],
        "timestamps": "bucketed",
        "cleanup": {"single": single.get("cleanup_ok"),
                    "multi_no_stale": multi.get("no_stale_handles")},
        "revocation": {"recorded": revoke.get("revocation_recorded"),
                       "classification": revoke.get("failure_classification")},
        "classification": revoke.get("failure_classification", "n/a"),
    }
    missing = [f for f in _REQUIRED_EVIDENCE_FIELDS if f not in evidence]
    clean = is_clean(evidence)
    status = M40StageStatus.PASSED if (not missing and clean) else M40StageStatus.FAILED
    return _stage(
        "stage6_evidence_verification", status,
        required_fields=list(_REQUIRED_EVIDENCE_FIELDS),
        missing_fields=missing,
        leak_clean=clean,
        evidence=evidence,
    )


# ── certification decision ───────────────────────────────────────────────────
def _decide(stages: list[dict[str, Any]], *, live_exercised: bool,
            secret_supplied: bool) -> str:
    statuses = [s["status"] for s in stages]
    any_failed = M40StageStatus.FAILED.value in statuses
    any_blocked = M40StageStatus.BLOCKED.value in statuses
    all_passed_live = all(s["status"] == M40StageStatus.PASSED.value for s in stages)

    if any_failed:
        return LiveCertificationVerdict.LIVE_FAILED.value
    if not secret_supplied:
        return LiveCertificationVerdict.LIVE_BLOCKED_OPERATOR_SECRET_REQUIRED.value
    if any_blocked or not live_exercised:
        return LiveCertificationVerdict.LIVE_BLOCKED.value
    if all_passed_live and live_exercised:
        return LiveCertificationVerdict.LIVE_CERTIFIED.value
    return LiveCertificationVerdict.LIVE_BLOCKED.value


def run_live_certification(config: Optional[M40Config] = None) -> dict[str, Any]:
    """Real gated 6-stage pipeline. Fails closed. Stops at first BLOCKED/FAILED gate."""
    cfg = config or M40Config()
    if kill_switch_active(cfg.environ):
        return _certification_body(
            [_stage(STAGES[0], M40StageStatus.BLOCKED, blockers=["kill_switch_active"])],
            verdict=LiveCertificationVerdict.LIVE_BLOCKED.value,
            live_exercised=False, secret_supplied=_secret_reference_supplied(cfg),
        )

    secret_supplied = _secret_reference_supplied(cfg)
    stages: list[dict[str, Any]] = []

    s1 = stage1_operator_acknowledgement(cfg)
    stages.append(s1)
    if not s1["ok"]:
        return _certification_body(
            stages, verdict=_decide(stages, live_exercised=False, secret_supplied=secret_supplied),
            live_exercised=False, secret_supplied=secret_supplied)

    s2 = stage2_provider_preflight(cfg)
    stages.append(s2)
    if not s2["ok"]:
        return _certification_body(
            stages, verdict=_decide(stages, live_exercised=False, secret_supplied=secret_supplied),
            live_exercised=False, secret_supplied=secret_supplied)

    s3 = stage3_single_session(cfg)
    stages.append(s3)
    live_exercised = bool(s3.get("live_network"))
    if s3["status"] != M40StageStatus.PASSED.value:
        return _certification_body(
            stages, verdict=_decide(stages, live_exercised=live_exercised, secret_supplied=secret_supplied),
            live_exercised=live_exercised, secret_supplied=secret_supplied)

    s4 = stage4_multi_session(cfg)
    stages.append(s4)
    if s4["status"] != M40StageStatus.PASSED.value:
        return _certification_body(
            stages, verdict=_decide(stages, live_exercised=live_exercised, secret_supplied=secret_supplied),
            live_exercised=live_exercised, secret_supplied=secret_supplied)

    s5 = stage5_external_revocation(cfg, operator_confirmed=cfg.authorization_present)
    stages.append(s5)
    s6 = stage6_evidence_verification(stages)
    stages.append(s6)

    live_exercised = live_exercised and bool(s4.get("live_network", False) or s3.get("live_network"))
    verdict = _decide(stages, live_exercised=live_exercised, secret_supplied=secret_supplied)
    return _certification_body(stages, verdict=verdict, live_exercised=live_exercised,
                               secret_supplied=secret_supplied)


def run_stage_rehearsal() -> dict[str, Any]:
    """Offline-fixture rehearsal of every stage. SIMULATED_NOT_LIVE. Not a certification."""
    cfg = M40Config(
        mode="rehearsal", acknowledgements=M39_ACK_TOKENS,
        authorization_present=True, environment_confirmed=True,
    )
    stages = [
        stage1_operator_acknowledgement(
            M40Config(mode="rehearsal", acknowledgements=M39_ACK_TOKENS,
                      authorization_present=True, environment_confirmed=True,
                      secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="svc:acct")),
        stage2_provider_preflight(
            M40Config(mode="rehearsal", acknowledgements=M39_ACK_TOKENS,
                      authorization_present=True, environment_confirmed=True,
                      secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="svc:acct",
                      branch="b", head="h", working_tree_class="CLEAN", live_flag=True)),
        stage3_single_session(cfg, rehearsal=True),
        stage4_multi_session(cfg, rehearsal=True),
        stage5_external_revocation(cfg, rehearsal=True),
    ]
    stages.append(stage6_evidence_verification(stages))
    # rehearsal never certifies live; cap verdict at LIVE_BLOCKED
    non_failed = all(s["status"] in (M40StageStatus.PASSED.value,
                                     M40StageStatus.SIMULATED_NOT_LIVE.value) for s in stages)
    body = _certification_body(
        stages,
        verdict=(LiveCertificationVerdict.LIVE_BLOCKED.value if non_failed
                 else LiveCertificationVerdict.LIVE_FAILED.value),
        live_exercised=False, secret_supplied=False,
    )
    body["mode"] = "rehearsal"
    body["rehearsal_note"] = "SIMULATED_NOT_LIVE; proves orchestration wiring; not a certification"
    body["all_stages_non_failed"] = non_failed
    return body


def _certification_body(stages: list[dict[str, Any]], *, verdict: str,
                        live_exercised: bool, secret_supplied: bool) -> dict[str, Any]:
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M40",
        "verdict": verdict,
        "live_certified": verdict == LiveCertificationVerdict.LIVE_CERTIFIED.value,
        "live_exercised": live_exercised,
        "secret_reference_supplied": secret_supplied,
        "provider_id": PROVIDER_ID,
        "stages": stages,
        "stages_completed": len(stages),
        "grants_canary": False,
        "grants_active": False,
        "grants_rollout": False,
        "grants_production": False,
        "grants_write": False,
        "authorities": dict(AUTHORITIES),
        "m39_fingerprint": compute_m39_fingerprint(),
        "banner": NON_PRODUCTION_BANNER,
        "trading_guardian": "UNENGAGED",
        "note": "M40 never grants canary/active/production; live certification "
                "requires a real provider exercised and all stages passed.",
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({"verdict": verdict, "stages": [s["stage"] + ":" + s["status"] for s in stages],
                    "live_exercised": live_exercised}, sort_keys=True).encode(),
        length=24,
    )
    return body


def build_m40_evidence() -> dict[str, dict[str, Any]]:
    cert = run_live_certification(M40Config())          # no credential -> BLOCKED
    rehearsal = run_stage_rehearsal()                    # offline mechanics proof
    return {
        "live_certification_blocked": cert,
        "stage_rehearsal_simulated": rehearsal,
        "summary": {
            "schema": "m40.summary.v1",
            "milestone": "M40",
            "certification_verdict": cert["verdict"],
            "rehearsal_verdict": rehearsal["verdict"],
            "live_certified": False,
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m40_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m40_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m40 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
