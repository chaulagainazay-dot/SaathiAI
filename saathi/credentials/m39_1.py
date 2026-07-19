"""M39.1 — Operator live-validation dry-run tooling (offline readiness extension).

Additive extension of M39. Composes M39 constants and gates; introduces NO new
credential / provider / session / lease / evidence system. Every function here is
fully offline and MUST NOT resolve or emit a secret value.

Provides operator-facing, pre-live tooling:
  * ``build_execution_plan``      — deterministic dry-run plan of what a live run
                                    would do (provider, endpoints, budgets, acks,
                                    env flags, secret-reference fingerprint).
  * ``render_command_preview``    — human-readable preview of the exact commands
                                    the operator would run (references, not values).
  * ``check_backend_availability``— offline structural + existence check of a
                                    secret *reference* backend (never a get()).
  * ``generate_revocation_checklist`` — step-by-step operator revocation checklist.
  * ``collect_offline_diagnostics``   — redacted environment/flag snapshot.
  * ``emit_m39_1_evidence``       — deterministic evidence bodies (no wall clock).

Authority state is UNCHANGED: no CANARY / ACTIVE / rollout / production / write.
All live-dependent outputs are one of NOT_EXERCISED / BLOCKED_OPERATOR_SECRET_REQUIRED
/ BLOCKED_OPERATOR_ACTION_REQUIRED / OFFLINE_ONLY / SIMULATED_NOT_LIVE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.backends import SecretBackend
from saathi.credentials.leakscan import is_clean, scan
from saathi.credentials.m39 import (
    AGGREGATE_CALL_BUDGET_DEFAULT,
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    APPROVED_LIVE_SOURCE_KINDS,
    AUTHORITIES,
    ENV_KILL_SWITCH,
    ENV_LIVE_FLAG,
    HARD_MAX_AGGREGATE,
    MAX_CONCURRENT_SESSIONS,
    M39_ACK_TOKENS,
    NON_PRODUCTION_BANNER,
    PER_SESSION_CALL_BUDGET,
    PROVIDER_ID,
    M39Error,
    _TOKEN_SHAPE,
    _hmac,
    compute_m39_fingerprint,
    kill_switch_active,
    live_flag_enabled,
    qualify_secret_reference,
    reference_fingerprint,
    resolve_secret_backend,
)

SCHEMA_VERSION = "m39_1.operator_dry_run.v1"
_FP_DOMAIN = b"saathi.m39_1.operator_dry_run.domain.v1"

# Live-dependent status vocabulary permitted for offline outputs.
LIVE_STATUS_NOT_EXERCISED = "NOT_EXERCISED"
LIVE_STATUS_BLOCKED_SECRET = "BLOCKED_OPERATOR_SECRET_REQUIRED"
LIVE_STATUS_BLOCKED_ACTION = "BLOCKED_OPERATOR_ACTION_REQUIRED"
LIVE_STATUS_OFFLINE_ONLY = "OFFLINE_ONLY"
LIVE_STATUS_SIMULATED = "SIMULATED_NOT_LIVE"

# Backend-availability verdicts (structural only — never based on secret value).
AVAIL_AVAILABLE = "AVAILABLE"          # reference present in backend
AVAIL_UNAVAILABLE = "UNAVAILABLE"      # reference confirmed absent
AVAIL_UNKNOWN = "UNKNOWN"              # existence could not be determined
AVAIL_BLOCKED_ACTION = LIVE_STATUS_BLOCKED_ACTION  # e.g. encrypted store needs wiring
AVAIL_SIMULATED = LIVE_STATUS_SIMULATED            # in-memory test fixture only


def _plan_fingerprint(plan: dict[str, Any]) -> str:
    payload = json.dumps(
        {k: plan[k] for k in sorted(plan) if k not in ("fingerprint",)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return _hmac(_FP_DOMAIN, payload, length=24)


# ── 1. dry-run execution plan ────────────────────────────────────────────────
def build_execution_plan(
    *,
    mode: str = "single",  # "single" | "multi"
    source_kind: str = "OS_KEYCHAIN_REFERENCE",
    locator: str = "",
    env_var_name: str = "",
    endpoints: tuple[str, ...] = ("/user", "/meta"),
    per_session_budget: int = PER_SESSION_CALL_BUDGET,
    aggregate_budget: int = AGGREGATE_CALL_BUDGET_DEFAULT,
    concurrency: int = 1,
    revocation_plan: str = "manual_github_pat_delete",
) -> dict[str, Any]:
    """Deterministic dry-run plan. Resolves NO secret; fails closed on bad shape.

    The plan states exactly what a live run *would* do without performing it.
    Live-dependent outcome fields remain NOT_EXERCISED.
    """
    if mode not in ("single", "multi"):
        raise M39Error("invalid_plan_mode", mode)

    k = (source_kind or "").strip().upper()
    problems: list[str] = []
    if k not in APPROVED_LIVE_SOURCE_KINDS:
        problems.append("unapproved_secret_backend")
    if locator and (_TOKEN_SHAPE.match(locator.strip()) or locator.startswith("raw:")):
        # never accept a raw secret as a locator, even in a plan
        raise M39Error("raw_secret_locator_rejected")
    if k == "ENV_REFERENCE" and _TOKEN_SHAPE.match((env_var_name or "").strip()):
        raise M39Error("raw_secret_locator_rejected")

    bad_ep = [e for e in endpoints if e.lstrip("/") not in {x.lstrip("/") for x in ALLOWED_ENDPOINTS}]
    if bad_ep:
        problems.append("endpoint_not_allowlisted")
    if not (1 <= per_session_budget <= PER_SESSION_CALL_BUDGET):
        problems.append("invalid_per_session_budget")
    if not (1 <= aggregate_budget <= HARD_MAX_AGGREGATE):
        problems.append("invalid_aggregate_budget")
    max_conc = 1 if mode == "single" else MAX_CONCURRENT_SESSIONS
    if not (1 <= concurrency <= max_conc):
        problems.append("invalid_concurrency")
    if not revocation_plan:
        problems.append("missing_revocation_plan")

    ref_fp = reference_fingerprint(k, locator) if k and locator else ""

    plan = {
        "schema": SCHEMA_VERSION,
        "kind": "execution_plan",
        "milestone": "M39.1",
        "mode": mode,
        "provider": PROVIDER_ID,
        "operations": {
            "endpoints": list(endpoints),
            "methods": sorted(ALLOWED_METHODS),
            "read_only": True,
            "writes": [],
        },
        "budgets": {
            "per_session_calls": per_session_budget,
            "aggregate_calls": aggregate_budget,
            "concurrency": concurrency,
            "hard_max_aggregate": HARD_MAX_AGGREGATE,
        },
        "secret_reference": {
            "source_kind": k,
            "locator_fingerprint": ref_fp,
            "resolves_plaintext_now": False,
            "env_var_name_present": bool(env_var_name) if k == "ENV_REFERENCE" else None,
        },
        "required_env_flags": {
            "live_flag": ENV_LIVE_FLAG,
            "kill_switch": ENV_KILL_SWITCH,
        },
        "required_acknowledgements": list(M39_ACK_TOKENS),
        "revocation_plan": revocation_plan,
        "authorities": dict(AUTHORITIES),
        "live_outcomes": {
            "single_session": LIVE_STATUS_NOT_EXERCISED,
            "multi_session": LIVE_STATUS_NOT_EXERCISED,
            "external_revocation": LIVE_STATUS_NOT_EXERCISED,
        },
        "plan_valid": not problems,
        "problems": problems,
        "banner": NON_PRODUCTION_BANNER,
        "trading_guardian": "UNENGAGED",
        "contains_secret_values": False,
    }
    plan["fingerprint"] = _plan_fingerprint(plan)
    return plan


# ── 2. human-readable command preview ────────────────────────────────────────
def render_command_preview(plan: dict[str, Any]) -> str:
    """Render the exact operator commands for a plan. Never prints a secret value."""
    if plan.get("kind") != "execution_plan":
        raise M39Error("not_an_execution_plan")
    sr = plan.get("secret_reference", {})
    fp = sr.get("locator_fingerprint") or "<REFERENCE_FINGERPRINT>"
    src = sr.get("source_kind") or "<SOURCE_KIND>"
    b = plan.get("budgets", {})
    mode = plan.get("mode", "single")
    ack_flags = " ".join(f'--ack {a}' for a in plan.get("required_acknowledgements", []))
    run_cmd = (
        "m39-run-live-single-session" if mode == "single" else "m39-run-live-multisession"
    )
    lines = [
        "M39.1 LIVE-VALIDATION COMMAND PREVIEW (dry-run — nothing is executed)",
        NON_PRODUCTION_BANNER,
        "",
        f"# provider={plan.get('provider')}  mode={mode}  "
        f"endpoints={','.join(plan.get('operations', {}).get('endpoints', []))}",
        f"# secret reference: source_kind={src} fingerprint={fp} "
        "(the secret VALUE is never shown or resolved here)",
        "",
        "# 1. export required environment (operator supplies the real reference):",
        f"export {plan.get('required_env_flags', {}).get('live_flag', ENV_LIVE_FLAG)}=1",
        "",
        "# 2. qualify the secret reference (no plaintext leaves the backend):",
        f"python -m saathi.credentials.cli m39-qualify-secret-reference "
        f"--source-kind {src} --locator <REFERENCE>",
        "",
        "# 3. preflight (fail-closed; must PASS before any live call):",
        f"python -m saathi.credentials.cli m39-preflight",
        "",
        "# 4. authorize live validation with all 10 acknowledgements:",
        f"python -m saathi.credentials.cli m39-authorize-live-validation "
        f"--source-kind {src} {ack_flags}",
        "",
        f"# 5. run bounded live {mode} session "
        f"(per_session={b.get('per_session_calls')} aggregate={b.get('aggregate_calls')} "
        f"concurrency={b.get('concurrency')}):",
        f"python -m saathi.credentials.cli {run_cmd} "
        f"--source-kind {src} --locator <REFERENCE>",
        "",
        "# 6. confirm external credential revocation after the run:",
        f"python -m saathi.credentials.cli m39-confirm-external-revocation",
        "",
        "# 7. evaluate canary ELIGIBILITY (read-only; never grants CANARY):",
        f"python -m saathi.credentials.cli m39-evaluate-canary-eligibility",
        "",
        f"# plan_valid={plan.get('plan_valid')} problems={plan.get('problems')}",
        "# authorities: CANARY/ACTIVE/rollout/production/write = NOT GRANTED",
    ]
    return "\n".join(lines)


# ── 3. secret-backend availability (offline, no resolution) ──────────────────
def check_backend_availability(
    *,
    source_kind: str,
    locator: str = "",
    env_var_name: str = "",
    backend: Optional[SecretBackend] = None,
    environ: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Structural availability of a secret-reference backend. Never calls get().

    Determines whether the reference is present without reading the secret value.
    Fails closed: any ambiguity yields UNKNOWN, never AVAILABLE.
    """
    k = (source_kind or "").strip().upper()
    result: dict[str, Any] = {
        "schema": "m39_1.backend_availability.v1",
        "kind": "backend_availability",
        "source_kind": k,
        "provider": PROVIDER_ID,
        "resolves_plaintext": False,
        "contains_secret_values": False,
        "authorities": dict(AUTHORITIES),
    }

    if k not in APPROVED_LIVE_SOURCE_KINDS:
        result.update(available=AVAIL_UNAVAILABLE, ready=False, reason="unapproved_secret_backend")
        return result
    if locator and (_TOKEN_SHAPE.match(locator.strip()) or locator.startswith("raw:")):
        raise M39Error("raw_secret_locator_rejected")

    if k == "ENCRYPTED_STORE_REFERENCE":
        # structural support only; operator must wire an approved store
        result.update(
            available=AVAIL_BLOCKED_ACTION,
            ready=False,
            reason="encrypted_store_requires_operator_wiring",
        )
        return result
    if k == "IN_MEMORY_TEST":
        result.update(
            available=AVAIL_SIMULATED,
            ready=False,
            reason="in_memory_test_backend_is_offline_fixture_only",
        )
        return result

    be = backend
    if be is None:
        try:
            be = resolve_secret_backend(
                k, locator=locator, env_var_name=env_var_name, environ=environ,
            )
        except M39Error as e:
            result.update(available=AVAIL_UNKNOWN, ready=False, reason=e.code)
            return result

    readiness: dict[str, Any] = {}
    try:
        readiness = dict(be.readiness()) if hasattr(be, "readiness") else {}
    except Exception:
        readiness = {}
    # guard: readiness must never carry a live-credential value
    readiness.pop("secret", None)
    readiness.pop("value", None)

    check_locator = locator if k != "ENV_REFERENCE" else (env_var_name or locator)
    exists: Optional[bool]
    try:
        exists = bool(be.exists(check_locator)) if check_locator else None
    except Exception:
        exists = None

    if exists is True:
        avail, ready, reason = AVAIL_AVAILABLE, True, "reference_present"
    elif exists is False:
        avail, ready, reason = AVAIL_UNAVAILABLE, False, "reference_absent"
    else:
        avail, ready, reason = AVAIL_UNKNOWN, False, "existence_undeterminable_fail_closed"

    result.update(
        available=avail,
        ready=ready,
        reason=reason,
        readiness=readiness,
        locator_fingerprint=reference_fingerprint(k, check_locator) if check_locator else "",
    )
    return result


# ── 4. revocation checklist generator ────────────────────────────────────────
def generate_revocation_checklist(
    *,
    provider: str = PROVIDER_ID,
    source_kind: str = "OS_KEYCHAIN_REFERENCE",
    locator: str = "",
) -> dict[str, Any]:
    """Deterministic operator revocation checklist. No secret value is included."""
    if provider != PROVIDER_ID:
        raise M39Error("provider_not_allowlisted", provider)
    if locator and (_TOKEN_SHAPE.match(locator.strip()) or locator.startswith("raw:")):
        raise M39Error("raw_secret_locator_rejected")
    k = (source_kind or "").strip().upper()
    ref_fp = reference_fingerprint(k, locator) if k and locator else ""

    steps = [
        {
            "id": "REV-1",
            "action": "Revoke the disposable GitHub PAT at GitHub → Settings → "
                      "Developer settings → Personal access tokens → Delete.",
            "operator_only": True,
            "verifies": "external_token_revocation",
        },
        {
            "id": "REV-2",
            "action": "Confirm the token no longer authenticates: "
                      "`curl -sS -o /dev/null -w '%{http_code}' -H 'Authorization: token <TOKEN>' "
                      "https://api.github.com/user` must return 401.",
            "operator_only": True,
            "verifies": "revocation_effective",
            "note": "Operator runs this outside SaathiOS; SaathiOS never handles the token value.",
        },
        {
            "id": "REV-3",
            "action": f"Remove the local secret reference from the backend "
                      f"(source_kind={k}, fingerprint={ref_fp or '<none>'}).",
            "operator_only": True,
            "verifies": "local_reference_removed",
        },
        {
            "id": "REV-4",
            "action": "Record revocation via "
                      "`m39-confirm-external-revocation` so evidence reflects it.",
            "operator_only": False,
            "verifies": "external_revocation_confirmation_recorded",
        },
        {
            "id": "REV-5",
            "action": "Run `m39-cleanup` / verify SecretHandle and session leases are "
                      "closed; confirm no SecretHandle remains open.",
            "operator_only": False,
            "verifies": "lease_and_handle_cleanup",
        },
    ]
    body = {
        "schema": "m39_1.revocation_checklist.v1",
        "kind": "revocation_checklist",
        "provider": provider,
        "source_kind": k,
        "locator_fingerprint": ref_fp,
        "steps": steps,
        "current_state": {
            "external_credential_revocation": LIVE_STATUS_NOT_EXERCISED,
            "reason": "no live credential exercised; checklist is preparatory",
        },
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
    }
    body["fingerprint"] = _plan_fingerprint(body)
    return body


def render_revocation_checklist(body: dict[str, Any]) -> str:
    """Human-readable revocation checklist."""
    if body.get("kind") != "revocation_checklist":
        raise M39Error("not_a_revocation_checklist")
    lines = [
        "M39.1 OPERATOR REVOCATION CHECKLIST",
        NON_PRODUCTION_BANNER,
        f"# provider={body.get('provider')} source_kind={body.get('source_kind')} "
        f"reference_fingerprint={body.get('locator_fingerprint') or '<none>'}",
        f"# external_credential_revocation: {body['current_state']['external_credential_revocation']}",
        "",
    ]
    for s in body.get("steps", []):
        who = "OPERATOR" if s.get("operator_only") else "SAATHIOS/OPERATOR"
        lines.append(f"[{s['id']}] ({who}) {s['action']}")
        if s.get("note"):
            lines.append(f"        note: {s['note']}")
        lines.append(f"        verifies: {s['verifies']}")
    return "\n".join(lines)


# ── 5. redacted offline diagnostics ──────────────────────────────────────────
def collect_offline_diagnostics(
    *, environ: Optional[dict[str, str]] = None
) -> dict[str, Any]:
    """Redacted snapshot of the M39 live-validation environment. No secret values."""
    return {
        "schema": "m39_1.diagnostics.v1",
        "kind": "offline_diagnostics",
        "provider": PROVIDER_ID,
        "m39_fingerprint": compute_m39_fingerprint(),
        "flags": {
            "live_flag_set": live_flag_enabled(environ),
            "kill_switch_active": kill_switch_active(environ),
        },
        "approved_secret_backends": sorted(APPROVED_LIVE_SOURCE_KINDS),
        "allowed_endpoints": sorted({e.lstrip("/") for e in ALLOWED_ENDPOINTS}),
        "allowed_methods": sorted(ALLOWED_METHODS),
        "budgets": {
            "per_session": PER_SESSION_CALL_BUDGET,
            "aggregate_default": AGGREGATE_CALL_BUDGET_DEFAULT,
            "max_concurrency": MAX_CONCURRENT_SESSIONS,
            "hard_max_aggregate": HARD_MAX_AGGREGATE,
        },
        "authorities": dict(AUTHORITIES),
        "live_state": {
            "single_session": LIVE_STATUS_NOT_EXERCISED,
            "multi_session": LIVE_STATUS_NOT_EXERCISED,
            "external_revocation": LIVE_STATUS_NOT_EXERCISED,
        },
        "trading_guardian": "UNENGAGED",
        "contains_secret_values": False,
    }


# ── 6. deterministic evidence emitter ────────────────────────────────────────
def build_m39_1_evidence() -> dict[str, dict[str, Any]]:
    """Build all M39.1 evidence bodies deterministically (no wall clock, no secret)."""
    plan_single = build_execution_plan(mode="single", locator="")
    plan_multi = build_execution_plan(mode="multi", concurrency=MAX_CONCURRENT_SESSIONS, locator="")
    avail_unapproved = check_backend_availability(source_kind="FORBIDDEN_KIND")
    avail_encrypted = check_backend_availability(source_kind="ENCRYPTED_STORE_REFERENCE")
    checklist = generate_revocation_checklist()
    diagnostics = collect_offline_diagnostics(environ={})
    return {
        "execution_plan_single": plan_single,
        "execution_plan_multi": plan_multi,
        "backend_availability_unapproved": avail_unapproved,
        "backend_availability_encrypted_store": avail_encrypted,
        "revocation_checklist": checklist,
        "offline_diagnostics": diagnostics,
        "summary": {
            "schema": "m39_1.summary.v1",
            "milestone": "M39.1",
            "verdict": "OFFLINE_OPERATOR_TOOLING_COMPLETE",
            "live_state": LIVE_STATUS_NOT_EXERCISED,
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_1_evidence(out_dir: str | Path) -> dict[str, Any]:
    """Write M39.1 evidence to disk. Leak-scans every body before writing."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_1_evidence()
    written: list[str] = []
    for name, body in bodies.items():
        assert is_clean(body), f"m39_1 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
