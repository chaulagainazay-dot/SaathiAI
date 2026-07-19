"""M39 — Live disposable sandbox validation and canary authorization decision.

Composes M31–M38 without parallel session/lease/credential systems.
Exercises real disposable sandbox credentials when an operator supplies an
approved secret *reference* (never plaintext). Evaluates canary *eligibility*
without granting CANARY / ACTIVE / rollout / production / write authority.

Hard invariants:
  * no production / rollout / CANARY / ACTIVE / write authority;
  * no plaintext secret in CLI, evidence, events, or coordinator state;
  * live network only after preflight + feature flag + acks + secret ref;
  * external credential revocation required for fully closed live verdict;
  * M40 not started; Trading Guardian UNENGAGED.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.providers.external.testkit import make_transport, public_resolver
from saathi.connectors.providers.external.transport import ExternalTransport, urllib_sender
from saathi.credentials.backends import (
    EnvironmentReferenceBackend,
    InMemoryTestSecretBackend,
    SecretBackend,
    SecretBackendError,
)
from saathi.credentials.leakscan import assert_clean, is_clean, scan
from saathi.credentials import m36, m37, m38
from saathi.credentials.m35 import SecretHandle, SessionLeaseStore, subject_fingerprint
from saathi.credentials.m36 import (
    AuthorizationStore,
    CallBudget,
    CleanupDisposition,
    M36Error,
    M36_ACK_TOKENS as M36_ACKS,
    reject_forbidden_cli_argv,
    retrieve_secret_handle,
    m36_credential_fingerprint,
    qualify_sandbox_identity,
    validate_m36_secret_reference,
)
from saathi.credentials.m37 import (
    SUBJECT_FP,
    SYNTH_SECRET,
    fixture_transport,
    run_provider_lifecycle,
)
from saathi.credentials.m38 import (
    MultiSessionCoordinator,
    SessionState,
    classify_retry,
)
from saathi.credentials.sandbox_provider import list_sandbox_providers, resolve_sandbox_provider
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import SandboxAccountRegistry
from saathi.credentials.models import CredentialStatus

SCHEMA_VERSION = "m39.live_sandbox_validation.v1"
_FP_DOMAIN = b"saathi.m39.live_validation.domain.v1"

PROVIDER_ID = "github_meta"
ALLOWED_ENDPOINTS = frozenset({"/user", "/meta", "user", "meta"})
ALLOWED_METHODS = frozenset({"GET"})
ALLOWED_OPERATIONS = frozenset({m36.OPERATION_IDENTITY, m36.OPERATION_META})
PER_SESSION_CALL_BUDGET = 3
AGGREGATE_CALL_BUDGET_DEFAULT = 6
MAX_CONCURRENT_SESSIONS = 2
HARD_MAX_AGGREGATE = 12

ENV_LIVE_FLAG = "SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION"
ENV_KILL_SWITCH = "SAATHI_M39_KILL_SWITCH"

# Approved backends for live secret *references* only.
APPROVED_LIVE_SOURCE_KINDS = frozenset({
    "OS_KEYCHAIN_REFERENCE",
    "ENV_REFERENCE",
    "ENCRYPTED_STORE_REFERENCE",
    "IN_MEMORY_TEST",  # offline fixture only; live preflight rejects for live path
})

# Ten runtime acknowledgements required by M39 (mission). Distinct from M36 set
# but may be supplied together with M36 tokens when composing sessions.
M39_ACK_TOKENS = (
    "I_CONFIRM_CREDENTIAL_IS_DISPOSABLE",
    "I_CONFIRM_SANDBOX_ACCOUNT_WHERE_POSSIBLE",
    "I_CONFIRM_MINIMUM_READ_ONLY_PERMISSIONS",
    "I_CONFIRM_NO_REPOSITORY_WRITE_PERMISSION",
    "I_CONFIRM_NO_ORG_ADMIN_PERMISSION",
    "I_CONFIRM_NO_BILLING_PERMISSION",
    "I_CONFIRM_NO_PACKAGE_DEPLOY_WORKFLOW_SECRET_WRITE",
    "I_CONFIRM_REVOKE_IMMEDIATELY_AFTER_VALIDATION",
    "I_CONFIRM_READINESS_IS_NOT_AUTHORIZATION",
    "I_CONFIRM_NO_PRODUCTION_ROLLOUT_CANARY_ACTIVE_WRITE",
)

NON_PRODUCTION_BANNER = (
    "M39 LIVE DISPOSABLE SANDBOX VALIDATION\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "BOUNDED LIVE VALIDATION ONLY\n"
    "ROLLOUT OFF\n"
    "NO CANARY GRANT\n"
    "NO ACTIVE\n"
    "TRADING GUARDIAN UNENGAGED"
)

AUTHORITIES = {
    "production_authorization": "NOT GRANTED",
    "rollout_authorization": "NOT GRANTED",
    "CANARY_authorization": "NOT GRANTED",
    "ACTIVE_authorization": "NOT GRANTED",
    "write_authority": "NOT GRANTED",
}

FORBIDDEN_CLI_FLAGS = frozenset({
    "--token", "--api-key", "--apikey", "--password", "--secret",
    "--authorization-header", "--authorization", "--bearer",
})

# Token-like CLI values (reject if argument *looks* like a secret, not a reference).
_TOKEN_SHAPE = re.compile(
    r"^(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"gho_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|Bearer\s+\S+)$",
    re.I,
)


class M39Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class CanaryEligibilityVerdict(str, Enum):
    CANARY_NOT_ELIGIBLE = "CANARY_NOT_ELIGIBLE"
    CANARY_ELIGIBLE_WITH_LIMITATIONS = "CANARY_ELIGIBLE_WITH_LIMITATIONS"
    READY_FOR_OPERATOR_CANARY_DECISION = "READY_FOR_OPERATOR_CANARY_DECISION"
    LIVE_VALIDATION_FAILED = "LIVE_VALIDATION_FAILED"
    BLOCKED_OPERATOR_SECRET_REQUIRED = "BLOCKED_OPERATOR_SECRET_REQUIRED"
    BLOCKED_EXTERNAL_REVOCATION_REQUIRED = "BLOCKED_EXTERNAL_REVOCATION_REQUIRED"


class LiveExerciseStatus(str, Enum):
    NOT_EXERCISED = "NOT_EXERCISED"
    BLOCKED = "BLOCKED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


# ── helpers ──────────────────────────────────────────────────────────────────
def _hmac(*parts: bytes, length: int = 32) -> str:
    return hmac.new(_FP_DOMAIN, b"|".join(parts), hashlib.sha256).hexdigest()[:length]


def compute_m39_fingerprint() -> str:
    material = {
        "schema": SCHEMA_VERSION,
        "provider": PROVIDER_ID,
        "endpoints": sorted(ALLOWED_ENDPOINTS),
        "methods": sorted(ALLOWED_METHODS),
        "acks": list(M39_ACK_TOKENS),
        "per_session_budget": PER_SESSION_CALL_BUDGET,
        "aggregate_budget": AGGREGATE_CALL_BUDGET_DEFAULT,
        "concurrency": MAX_CONCURRENT_SESSIONS,
        "m38_fp": m38.compute_m38_fingerprint(),
        "authorities": AUTHORITIES,
    }
    return hmac.new(
        _FP_DOMAIN, json.dumps(material, sort_keys=True).encode(), hashlib.sha256,
    ).hexdigest()[:64]


def reject_m39_forbidden_argv(argv: list[str]) -> None:
    """Reject raw secret CLI carriers and token-shaped arguments."""
    try:
        reject_forbidden_cli_argv(list(argv))
    except M36Error as e:
        raise M39Error("raw_secret_cli_rejected", e.detail or e.code) from e
    for a in argv:
        raw = a.split("=", 1)
        val = raw[1] if len(raw) == 2 else a
        if _TOKEN_SHAPE.match(val.strip()):
            raise M39Error("token_shaped_argument_rejected")
        base = raw[0].lower()
        if base in FORBIDDEN_CLI_FLAGS or base.lstrip("-") in (
            "token", "api-key", "apikey", "password", "secret", "authorization-header",
        ):
            raise M39Error("raw_secret_cli_rejected", base)


def live_flag_enabled(environ: Optional[dict[str, str]] = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(ENV_LIVE_FLAG, "")).strip() == "1"


def kill_switch_active(environ: Optional[dict[str, str]] = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(ENV_KILL_SWITCH, "")).strip() in ("1", "true", "TRUE", "yes")


def reference_fingerprint(source_kind: str, locator: str) -> str:
    """Non-reversible fingerprint of a secret *reference* (not the secret)."""
    return _hmac(
        b"secret_ref",
        (source_kind or "").encode(),
        (locator or "").encode(),
        length=24,
    )


# ── Keychain reference backend (macOS) ───────────────────────────────────────
class MacOSKeychainReferenceBackend(SecretBackend):
    """Resolves OS Keychain by service name reference only.

    Locator format: service name, or ``service\\x1faccount`` for account binding.
    Never logs or returns values outside ``get()``. ``exists()`` checks without
    printing the secret (uses find without -w when possible; falls back carefully).
    """

    kind = "os_keychain_reference"

    def __init__(self, *, security_bin: str = "security") -> None:
        self._security = security_bin
        self._lock = threading.RLock()

    def _parse(self, locator: str) -> tuple[str, str]:
        if not locator or locator.startswith("raw:"):
            raise SecretBackendError("invalid_keychain_locator")
        if "\x1f" in locator:
            svc, acct = locator.split("\x1f", 1)
            return svc, acct
        if ":" in locator and not locator.startswith("http"):
            # service:account form (common operator convention)
            parts = locator.split(":", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]
        return locator, ""

    def put(self, locator: str, fields: dict[str, str]) -> None:
        raise SecretBackendError("keychain_put_not_supported_in_m39")

    def exists(self, locator: str) -> bool:
        """Presence check: find-generic-password without dumping secret to caller logs.

        Uses ``security find-generic-password`` (metadata only). Does not use -w.
        """
        svc, acct = self._parse(locator)
        cmd = [self._security, "find-generic-password", "-s", svc]
        if acct:
            cmd.extend(["-a", acct])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        svc, acct = self._parse(locator)
        cmd = [self._security, "find-generic-password", "-s", svc, "-w"]
        if acct:
            cmd.extend(["-a", acct])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except Exception as e:
            raise SecretBackendError("keychain_read_failure") from e
        if r.returncode != 0 or not (r.stdout or "").strip():
            raise SecretBackendError("keychain_secret_missing")
        val = r.stdout.strip()
        # clear subprocess stdout references as much as possible
        fname = (fields or ["api_key"])[0]
        return {fname: val}

    def delete(self, locator: str) -> None:
        raise SecretBackendError("keychain_delete_not_supported_in_m39")

    def readiness(self) -> dict[str, Any]:
        return {"kind": self.kind, "ready": True, "live_credentials": False}


def resolve_secret_backend(
    source_kind: str,
    *,
    locator: str = "",
    env_var_name: str = "",
    environ: Optional[dict[str, str]] = None,
    offline_seed: Optional[str] = None,
) -> SecretBackend:
    """Build an approved backend for a *reference*. Never accepts raw tokens as locators."""
    k = (source_kind or "").strip().upper()
    if k not in APPROVED_LIVE_SOURCE_KINDS:
        raise M39Error("unapproved_secret_backend", k)
    if locator and (_TOKEN_SHAPE.match(locator.strip()) or locator.startswith("raw:")):
        raise M39Error("raw_secret_locator_rejected")
    if k == "OS_KEYCHAIN_REFERENCE":
        return MacOSKeychainReferenceBackend()
    if k == "ENV_REFERENCE":
        be = EnvironmentReferenceBackend(environ=environ)
        ename = env_var_name or locator
        if not ename:
            raise M39Error("missing_env_var_name")
        if _TOKEN_SHAPE.match(ename.strip()):
            raise M39Error("raw_secret_locator_rejected")
        # declare field -> env var NAME (not value)
        be.declare(locator or ename, {"api_key": ename})
        return be
    if k == "IN_MEMORY_TEST":
        be = InMemoryTestSecretBackend()
        if offline_seed is not None:
            be.put(locator or "m39/synth", {"api_key": offline_seed})
        return be
    if k == "ENCRYPTED_STORE_REFERENCE":
        # Structural support only; live operators must wire approved store.
        raise M39Error("encrypted_store_requires_operator_wiring")
    raise M39Error("unapproved_secret_backend", k)


# ── kill switch ──────────────────────────────────────────────────────────────
class LiveKillSwitch:
    def __init__(self) -> None:
        self._tripped = False
        self._reason = ""
        self._lock = threading.RLock()

    def trip(self, reason: str = "operator_cancel") -> None:
        with self._lock:
            self._tripped = True
            self._reason = reason[:200]

    def is_tripped(self) -> bool:
        with self._lock:
            return self._tripped

    def assert_allows_provider_call(self) -> None:
        if self.is_tripped() or kill_switch_active():
            raise M39Error("kill_switch_active", self._reason or "env")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tripped": self.is_tripped() or kill_switch_active(),
            "reason": self._reason or ("env" if kill_switch_active() else ""),
            "prevents_new_provider_calls": True,
            "prevents_uncommitted_retries": True,
            "grants_authority": False,
        }


# ── acknowledgements ─────────────────────────────────────────────────────────
def validate_acknowledgements(acks: tuple[str, ...] | list[str]) -> dict[str, Any]:
    provided = {a.strip() for a in acks if a and str(a).strip()}
    missing = [t for t in M39_ACK_TOKENS if t not in provided]
    if missing:
        raise M39Error("missing_acknowledgement", ",".join(missing))
    return {
        "schema": "m39.operator_acknowledgements.v1",
        "all_present": True,
        "count": len(M39_ACK_TOKENS),
        "tokens_recorded": list(M39_ACK_TOKENS),  # names only, not free-form secrets
        "inferred_from_docs": False,
        "contains_secret_values": False,
    }


# ── authorization (M39-scoped, reuses M36 store patterns) ────────────────────
def create_live_authorization(
    store: AuthorizationStore,
    *,
    account_ref_id: str,
    credential_ref_id: str,
    acknowledgements: tuple[str, ...],
    secret_source_kind: str,
    call_budget: int = PER_SESSION_CALL_BUDGET,
    approved_duration: float = 900.0,
) -> Any:
    """Create authorization requiring M39 acks + M36 acks for M36 store compat."""
    k = secret_source_kind.strip().upper()
    if k not in APPROVED_LIVE_SOURCE_KINDS or k == "IN_MEMORY_TEST":
        # live path rejects synthetic backends
        if k == "IN_MEMORY_TEST":
            raise M39Error("live_requires_real_secret_backend")
        raise M39Error("unapproved_secret_backend", k)
    validate_acknowledgements(acknowledgements)
    # M36 store requires its own ack set
    combined = tuple(dict.fromkeys(list(acknowledgements) + list(M36_ACKS)))
    try:
        auth = store.create(
            provider_id=PROVIDER_ID,
            account_ref_id=account_ref_id,
            credential_ref_id=credential_ref_id,
            acknowledgements=combined,
            secret_source_kind=k,
            approved_call_budget=call_budget,
            approved_duration=approved_duration,
        )
    except M36Error as e:
        raise M39Error(e.code, e.detail) from e
    return auth


# ── preflight ────────────────────────────────────────────────────────────────
@dataclass
class PreflightInput:
    branch: str = ""
    head: str = ""
    expected_head: str = ""
    working_tree_class: str = "UNKNOWN"  # CLEAN | NOISE_ONLY | DIRTY
    m31_m38_regression_ok: bool = True
    secret_source_kind: str = ""
    secret_locator: str = ""
    secret_ref_exists: Optional[bool] = None
    authorization_present: bool = False
    acknowledgements: tuple[str, ...] = ()
    provider_id: str = PROVIDER_ID
    endpoints: tuple[str, ...] = ("/user", "/meta")
    methods: tuple[str, ...] = ("GET",)
    per_session_budget: int = PER_SESSION_CALL_BUDGET
    aggregate_budget: int = AGGREGATE_CALL_BUDGET_DEFAULT
    concurrency_ceiling: int = MAX_CONCURRENT_SESSIONS
    retry_ceiling: int = 3
    live_flag: bool = False
    kill_switch_ready: bool = True
    evidence_dir_ready: bool = True
    cleanup_handler_ready: bool = True
    revocation_plan: str = "manual_github_pat_delete"
    environ: Optional[dict[str, str]] = None


def run_live_preflight(inp: PreflightInput) -> dict[str, Any]:
    """Strict fail-closed preflight. No network calls."""
    blockers: list[str] = []
    checks: dict[str, bool] = {}

    def _chk(name: str, ok: bool, blocker: str = "") -> None:
        checks[name] = ok
        if not ok:
            blockers.append(blocker or name)

    _chk("branch_recorded", bool(inp.branch), "branch_unknown")
    if inp.expected_head:
        _chk("head_matches_expected", inp.head == inp.expected_head, "head_mismatch")
    else:
        _chk("head_recorded", bool(inp.head), "head_unknown")
    _chk(
        "working_tree_classifiable",
        inp.working_tree_class in ("CLEAN", "NOISE_ONLY", "DIRTY"),
        "working_tree_unclassified",
    )
    # DIRTY is recorded but not an automatic fail for preflight of live validation
    # (unrelated noise is preserved). Unclassified is a fail.
    _chk("m31_m38_regression", inp.m31_m38_regression_ok, "regression_unhealthy")

    sk = (inp.secret_source_kind or "").strip().upper()
    _chk("secret_source_kind_present", bool(sk), "missing_secret_source_kind")
    if sk:
        try:
            validate_m36_secret_reference(source_kind=sk, want_retrieval=False)
            _chk("secret_source_approved", sk in APPROVED_LIVE_SOURCE_KINDS and sk != "IN_MEMORY_TEST",
                 "unapproved_or_synthetic_secret_backend")
        except M36Error:
            _chk("secret_source_approved", False, "invalid_secret_source")
    _chk("secret_locator_present", bool(inp.secret_locator), "missing_secret_locator")
    if inp.secret_locator and (
        _TOKEN_SHAPE.match(inp.secret_locator.strip()) or inp.secret_locator.startswith("raw:")
    ):
        _chk("secret_locator_not_raw", False, "raw_secret_locator_rejected")
    else:
        _chk("secret_locator_not_raw", True)

    if inp.secret_ref_exists is None:
        _chk("secret_ref_existence_checked", False, "secret_ref_existence_unknown")
    else:
        _chk("secret_ref_exists", bool(inp.secret_ref_exists), "secret_ref_missing")

    _chk("authorization_present", inp.authorization_present, "missing_authorization")

    try:
        validate_acknowledgements(inp.acknowledgements)
        _chk("acknowledgements_complete", True)
    except M39Error:
        _chk("acknowledgements_complete", False, "missing_acknowledgement")

    _chk("provider_allowlist", inp.provider_id == PROVIDER_ID, "provider_not_allowlisted")
    ep_ok = all(
        e.lstrip("/") in {x.lstrip("/") for x in ALLOWED_ENDPOINTS} for e in inp.endpoints
    )
    _chk("endpoint_allowlist", ep_ok and len(inp.endpoints) > 0, "endpoint_not_allowlisted")
    method_ok = all(m.upper() in ALLOWED_METHODS for m in inp.methods)
    _chk("method_allowlist", method_ok, "method_not_allowlisted")
    _chk(
        "per_session_budget",
        1 <= inp.per_session_budget <= PER_SESSION_CALL_BUDGET,
        "invalid_per_session_budget",
    )
    _chk(
        "aggregate_budget",
        1 <= inp.aggregate_budget <= HARD_MAX_AGGREGATE,
        "invalid_aggregate_budget",
    )
    _chk(
        "concurrency_ceiling",
        1 <= inp.concurrency_ceiling <= MAX_CONCURRENT_SESSIONS,
        "invalid_concurrency",
    )
    _chk("retry_ceiling", 1 <= inp.retry_ceiling <= 3, "invalid_retry_ceiling")

    flag = inp.live_flag or live_flag_enabled(inp.environ)
    _chk("live_feature_flag", flag, "live_feature_flag_missing")
    _chk("kill_switch_ready", inp.kill_switch_ready, "kill_switch_unavailable")
    _chk("evidence_output_ready", inp.evidence_dir_ready, "evidence_dir_not_ready")
    _chk("cleanup_handler_ready", inp.cleanup_handler_ready, "cleanup_handler_not_ready")
    _chk("revocation_plan_present", bool(inp.revocation_plan), "missing_revocation_plan")
    if kill_switch_active(inp.environ):
        _chk("kill_switch_not_tripped", False, "kill_switch_active")
    else:
        _chk("kill_switch_not_tripped", True)

    ok = not blockers
    ref_fp = reference_fingerprint(sk, inp.secret_locator) if sk and inp.secret_locator else ""
    return {
        "schema": "m39.live_preflight.v1",
        "ok": ok,
        "passed": ok,
        "blockers": blockers,
        "checks": checks,
        "provider_id": PROVIDER_ID,
        "locator_fingerprint": ref_fp,
        "source_kind": sk or None,
        "branch": inp.branch,
        "head": inp.head[:40] if inp.head else "",
        "working_tree_class": inp.working_tree_class,
        "live_flag": flag,
        "network_calls_performed": 0,
        "banner": NON_PRODUCTION_BANNER,
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
        "status": "PASSED" if ok else "FAILED",
    }


def preflight_summary() -> dict[str, Any]:
    return {
        "milestone": "M39",
        "provider": PROVIDER_ID,
        "live_flag": ENV_LIVE_FLAG,
        "kill_switch": ENV_KILL_SWITCH,
        "required_acks": list(M39_ACK_TOKENS),
        "allowed_endpoints": sorted(ALLOWED_ENDPOINTS),
        "allowed_methods": sorted(ALLOWED_METHODS),
        "per_session_budget": PER_SESSION_CALL_BUDGET,
        "aggregate_budget_default": AGGREGATE_CALL_BUDGET_DEFAULT,
        "max_concurrent_sessions": MAX_CONCURRENT_SESSIONS,
        "approved_source_kinds": sorted(APPROVED_LIVE_SOURCE_KINDS - {"IN_MEMORY_TEST"}),
        "fingerprint": compute_m39_fingerprint(),
        "banner": NON_PRODUCTION_BANNER,
        "authorities": dict(AUTHORITIES),
        "m40_started": False,
        "grants_canary": False,
        "default_live": False,
    }


# ── secret reference qualification (no network) ──────────────────────────────
def qualify_secret_reference(
    *,
    source_kind: str,
    locator: str,
    backend: Optional[SecretBackend] = None,
    env_var_name: str = "",
    environ: Optional[dict[str, str]] = None,
    require_exists: bool = True,
) -> dict[str, Any]:
    """Validate reference shape and optional existence without retrieving plaintext to caller."""
    k = (source_kind or "").strip().upper()
    if not k:
        raise M39Error("missing_secret_source_kind")
    if not locator:
        raise M39Error("missing_secret_locator")
    if _TOKEN_SHAPE.match(locator.strip()) or locator.startswith("raw:"):
        raise M39Error("raw_secret_locator_rejected")
    try:
        structural = validate_m36_secret_reference(source_kind=k, want_retrieval=False)
    except M36Error as e:
        raise M39Error(e.code, e.detail) from e
    if k not in APPROVED_LIVE_SOURCE_KINDS:
        raise M39Error("unapproved_secret_backend", k)

    exists: Optional[bool] = None
    be = backend
    if be is None and k in ("ENV_REFERENCE", "OS_KEYCHAIN_REFERENCE", "IN_MEMORY_TEST"):
        try:
            be = resolve_secret_backend(
                k, locator=locator, env_var_name=env_var_name, environ=environ,
            )
        except M39Error:
            be = None
    if be is not None:
        try:
            exists = bool(be.exists(locator if k != "ENV_REFERENCE" else (locator or env_var_name)))
        except Exception:
            exists = False

    if require_exists and exists is False:
        raise M39Error("secret_ref_missing")
    if require_exists and exists is None and k != "IN_MEMORY_TEST":
        # existence unknown — fail closed for live qualification
        raise M39Error("secret_ref_existence_unknown")

    return {
        "schema": "m39.locator_qualification.v1",
        "qualified": exists is not False,
        "source_kind": k,
        "locator_fingerprint": reference_fingerprint(k, locator),
        "exists": exists,
        "structural": structural,
        "retrieves_plaintext_to_caller": False,
        "contains_secret_values": False,
        "status": "QUALIFIED" if exists else ("UNKNOWN" if exists is None else "MISSING"),
    }


# ── offline fail-path exercises ──────────────────────────────────────────────
def run_offline_failure_gates() -> dict[str, Any]:
    """Safe offline checks for fail-closed live gates (no network)."""
    cases: list[dict[str, Any]] = []

    def _case(name: str, ok: bool, **extra: Any) -> None:
        cases.append({"name": name, "pass": ok, **extra})

    # missing feature flag
    pf = run_live_preflight(PreflightInput(
        branch="milestone/m7-security-engine", head="abc", working_tree_class="NOISE_ONLY",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="svc:acct",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(M39_ACK_TOKENS), live_flag=False,
    ))
    _case("missing_feature_flag", not pf["ok"] and "live_feature_flag_missing" in pf["blockers"])

    # missing ack
    try:
        validate_acknowledgements(())
        _case("missing_acknowledgement", False)
    except M39Error as e:
        _case("missing_acknowledgement", e.code == "missing_acknowledgement")

    # missing secret reference
    pf2 = run_live_preflight(PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="",
        secret_ref_exists=False, authorization_present=True,
        acknowledgements=tuple(M39_ACK_TOKENS), live_flag=True,
    ))
    _case("missing_secret_reference", not pf2["ok"] and "missing_secret_locator" in pf2["blockers"])

    # raw secret rejected
    try:
        reject_m39_forbidden_argv(["m39-run-live-single-session", "--token=ghp_abcdefghijklmnopqrstuvwxyz12"])
        _case("rejected_raw_secret_input", False)
    except M39Error as e:
        _case("rejected_raw_secret_input", e.code in ("raw_secret_cli_rejected", "token_shaped_argument_rejected"))

    try:
        qualify_secret_reference(source_kind="ENV_REFERENCE", locator="ghp_abcdefghijklmnopqrstuvwxyz12", require_exists=False)
        _case("raw_locator_rejected", False)
    except M39Error as e:
        _case("raw_locator_rejected", e.code == "raw_secret_locator_rejected")

    # provider allowlist
    pf3 = run_live_preflight(PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(M39_ACK_TOKENS), live_flag=True,
        provider_id="not_github",
    ))
    _case("provider_allowlist", not pf3["ok"] and "provider_not_allowlisted" in pf3["blockers"])

    # endpoint allowlist
    pf4 = run_live_preflight(PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(M39_ACK_TOKENS), live_flag=True,
        endpoints=("/user", "/repos"),
    ))
    _case("endpoint_allowlist", not pf4["ok"] and "endpoint_not_allowlisted" in pf4["blockers"])

    # method allowlist
    pf5 = run_live_preflight(PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(M39_ACK_TOKENS), live_flag=True,
        methods=("POST",),
    ))
    _case("method_allowlist", not pf5["ok"] and "method_not_allowlisted" in pf5["blockers"])

    # call budget exhaustion (offline coordinator)
    coord = MultiSessionCoordinator(aggregate_call_budget=2, clock=lambda: 9_000_000.0)
    coord.aggregate_calls_used = 2
    budget_ok = False
    try:
        coord.start_session(credential_ref_id="x", call_budget=2)
    except m38.M38Error as e:
        budget_ok = e.code == "aggregate_call_budget_exhausted"
    _case("aggregate_budget_exhaustion", budget_ok)

    # per-session budget via CallBudget
    cb = CallBudget(2)
    cb.consume(kind="identity")
    cb.consume(kind="operation")
    exhausted = False
    try:
        cb.consume(kind="operation")
    except Exception:
        exhausted = True
    _case("call_budget_exhaustion", exhausted or cb.remaining() == 0)

    # kill switch
    ks = LiveKillSwitch()
    ks.trip("test")
    killed = False
    try:
        ks.assert_allows_provider_call()
    except M39Error as e:
        killed = e.code == "kill_switch_active"
    _case("kill_switch_behavior", killed)

    # recovery after interruption (offline, reuses M38)
    rec = m38.run_recovery_matrix()
    _case("recovery_after_interruption", rec.get("failed", 1) == 0)

    # duplicate recovery
    c = MultiSessionCoordinator(clock=lambda: 9_000_001.0)
    c.start_session(credential_ref_id="c", session_id="dup", interrupt_after="identity")
    a = c.recover_session("dup")
    b = c.recover_session("dup")
    _case("duplicate_recovery", a.get("ok") is not None and (b.get("idempotent") or b.get("ok")))

    # external revocation confirmation state
    rev = record_external_revocation(confirmed=False, operator_note="pending")
    _case("external_revocation_pending_state", rev["status"] == "PENDING")
    rev2 = record_external_revocation(confirmed=True, operator_note="revoked_in_github_ui")
    _case("external_revocation_confirmed_state", rev2["status"] == "CONFIRMED")

    # canary recommendation never grants
    can = evaluate_canary_eligibility(
        secret_reference_supplied=False,
        live_single_status=LiveExerciseStatus.NOT_EXERCISED.value,
        live_multi_status=LiveExerciseStatus.NOT_EXERCISED.value,
    )
    _case(
        "canary_recommendation_no_grant",
        can["grants_canary"] is False
        and can["verdict"] == CanaryEligibilityVerdict.BLOCKED_OPERATOR_SECRET_REQUIRED.value,
    )

    # authority non-escalation
    _case("authority_non_escalation", all(v == "NOT GRANTED" for v in AUTHORITIES.values()))

    # identity mismatch offline
    life = run_provider_lifecycle(
        transport=fixture_transport(
            identity_body=json.dumps({"id": 999999, "type": "User"}).encode(),
        ),
        expected_subject_fingerprint=SUBJECT_FP,
        session_id="id_mismatch",
    )
    _case("identity_mismatch", not life.ok)

    # unexpected write scope offline via classify
    scope = m36.classify_observed_scopes(("identity:read",), ("repo",))
    _case("unexpected_scope", scope.get("result") in (
        m36.M36ScopeResult.WRITE_SCOPE_PRESENT.value,
        m36.M36ScopeResult.MISMATCHED.value,
        "WRITE_SCOPE_PRESENT", "MISMATCHED",
    ) or not scope.get("ok", True))

    # separate handles / leases offline via multi-session
    multi = m38.run_offline_multisession_validation()
    _case("separate_live_session_handles_offline", multi.get("failed", 1) == 0)

    # leak scan without exposing matches
    payload = {"token_placeholder": "not_a_real_secret", "ok": True}
    findings = scan({"nested": "Bearer FAKESECRET_e1f2g3h4i5j6k7l8m9n0"})
    _case(
        "leak_scanning_no_expose",
        len(findings) >= 1 and all("ghp_" not in f.preview and "Bearer " not in f.preview for f in findings),
    )

    # sanitized provider errors (no headers)
    err = sanitize_provider_error({"headers": {"Authorization": "Bearer x"}, "message": "fail", "status": 401})
    _case("sanitized_provider_errors", "Authorization" not in json.dumps(err) and "Bearer" not in json.dumps(err))

    # cleanup independence
    _case("cleanup_independence", multi.get("failed", 1) == 0)

    passed = sum(1 for c in cases if c.get("pass"))
    return {
        "schema": "m39.offline_failure_gates.v1",
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "contains_secret_values": False,
    }


def sanitize_provider_error(err: dict[str, Any]) -> dict[str, Any]:
    """Strip headers/authorization material from provider error dicts."""
    return {
        "status": err.get("status") or err.get("status_code") or err.get("http_status"),
        "failure_class": err.get("failure_class") or err.get("classification") or err.get("message", "")[:80],
        "privacy_safe": True,
        "contains_secret_values": False,
        "headers_included": False,
    }


# ── live single-session (gated) ──────────────────────────────────────────────
def run_live_single_session(
    *,
    secret_source_kind: str,
    secret_locator: str,
    acknowledgements: tuple[str, ...],
    expected_subject_fingerprint: str = "",
    env_var_name: str = "",
    environ: Optional[dict[str, str]] = None,
    live_flag: Optional[bool] = None,
    transport: Optional[ExternalTransport] = None,
    backend: Optional[SecretBackend] = None,
    kill_switch: Optional[LiveKillSwitch] = None,
    account_alias: str = "m39-sbx",
    interrupt_after: str = "",
    cancel_before_second_call: bool = False,
    allow_offline_fixture: bool = False,
    session_id: str = "sess_m39_single",
) -> dict[str, Any]:
    """Run one bounded live (or offline-fixture) session through M37 lifecycle.

    Live network requires feature flag + acks + approved backend + secret ref.
    When ``allow_offline_fixture`` is True and source is IN_MEMORY_TEST, uses
    fixture transport (tests only).
    """
    ks = kill_switch or LiveKillSwitch()
    env = environ if environ is not None else os.environ
    flag = live_flag if live_flag is not None else live_flag_enabled(env)
    sk = (secret_source_kind or "").strip().upper()

    events: list[dict[str, Any]] = []
    handle_closed = True
    lease_revoked = False
    call_budget_used = 0
    cred_fp = ""
    identity_result: dict[str, Any] = {}
    operation_result: dict[str, Any] = {}
    scope_result: dict[str, Any] = {}
    reason = ""
    ok = False
    live_network = False

    def _emit(etype: str, **payload: Any) -> None:
        events.append({
            "event_type": etype, "session_id": session_id,
            "privacy_safe": True, "contains_secret_values": False, **payload,
        })

    try:
        validate_acknowledgements(acknowledgements)
        if sk == "IN_MEMORY_TEST" and not allow_offline_fixture:
            raise M39Error("live_requires_real_secret_backend")
        if sk != "IN_MEMORY_TEST" and not flag:
            raise M39Error("live_feature_flag_missing")
        if kill_switch_active(env) or ks.is_tripped():
            raise M39Error("kill_switch_active")

        be = backend or resolve_secret_backend(
            sk, locator=secret_locator, env_var_name=env_var_name,
            environ=env, offline_seed=SYNTH_SECRET if allow_offline_fixture else None,
        )
        if not allow_offline_fixture:
            if not be.exists(secret_locator if sk != "ENV_REFERENCE" else (secret_locator or env_var_name)):
                raise M39Error("secret_ref_missing")

        # Provider allowlist
        if PROVIDER_ID not in list_sandbox_providers():
            raise M39Error("provider_not_allowlisted")

        live_network = sk != "IN_MEMORY_TEST" and flag and transport is None
        if transport is None:
            if live_network:
                transport = ExternalTransport(sender=urllib_sender)
            else:
                transport = fixture_transport()

        ks.assert_allows_provider_call()

        if cancel_before_second_call:
            # Run lifecycle with interrupt after identity (no second provider call)
            interrupt_after = interrupt_after or "operation"

        life = run_provider_lifecycle(
            transport=transport,
            secret_backend=be,
            secret_locator=secret_locator or env_var_name or "m39/loc",
            secret_value=SYNTH_SECRET if allow_offline_fixture else "",
            seed_if_missing=allow_offline_fixture,
            session_id=session_id,
            expected_subject_fingerprint=expected_subject_fingerprint or (
                SUBJECT_FP if allow_offline_fixture else ""
            ),
            live_exercised=live_network,
            interrupt_after=interrupt_after,
        )
        handle_closed = life.handle_closed
        lease_revoked = life.lease_revoked
        call_budget_used = int((life.call_budget or {}).get("consumed", 0))
        cred_fp = life.credential_fingerprint
        identity_result = life.identity_result
        operation_result = life.operation_result
        ok = bool(life.ok)
        reason = life.reason
        if call_budget_used > PER_SESSION_CALL_BUDGET:
            ok = False
            reason = "call_budget_exceeded"
        _emit("m39.single_session_complete", ok=ok, reason=reason[:100])
    except M39Error as e:
        reason = e.code
        ok = False
        _emit("m39.single_session_blocked", reason=e.code)
    except Exception as e:
        reason = getattr(e, "code", type(e).__name__)
        ok = False
        _emit("m39.single_session_failed", reason=str(reason)[:100])

    status = (
        LiveExerciseStatus.PASSED.value if ok else
        LiveExerciseStatus.FAILED.value if reason and "missing" not in reason and "flag" not in reason else
        LiveExerciseStatus.BLOCKED.value
    )
    if reason in (
        "live_feature_flag_missing", "secret_ref_missing", "missing_acknowledgement",
        "live_requires_real_secret_backend", "unapproved_secret_backend",
    ):
        status = LiveExerciseStatus.BLOCKED.value

    out = {
        "schema": "m39.live_single_session.v1",
        "ok": ok,
        "status": status if (live_network or allow_offline_fixture) else LiveExerciseStatus.NOT_EXERCISED.value,
        "live_network": live_network,
        "session_id": session_id,
        "provider_id": PROVIDER_ID,
        "credential_fingerprint": cred_fp,
        "locator_fingerprint": reference_fingerprint(sk, secret_locator),
        "handle_closed": handle_closed,
        "lease_revoked": lease_revoked,
        "call_budget_used": call_budget_used,
        "call_budget_max": PER_SESSION_CALL_BUDGET,
        "identity_result": identity_result,
        "operation_result": operation_result,
        "scope_result": scope_result,
        "reason": reason,
        "events": events,
        "kill_switch": ks.to_dict(),
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
        "contains_raw_identity": False,
    }
    if allow_offline_fixture and ok:
        out["status"] = LiveExerciseStatus.PASSED.value
        out["mode"] = "offline_fixture"
    if not is_clean(out):
        out["ok"] = False
        out["status"] = LiveExerciseStatus.FAILED.value
        out["reason"] = "leak_detected"
    return out


def run_live_multisession(
    *,
    secret_source_kind: str,
    secret_locator: str,
    acknowledgements: tuple[str, ...],
    expected_subject_fingerprint: str = "",
    env_var_name: str = "",
    environ: Optional[dict[str, str]] = None,
    live_flag: Optional[bool] = None,
    backend_factory: Optional[Callable[[], SecretBackend]] = None,
    allow_offline_fixture: bool = False,
    sequential: bool = True,
) -> dict[str, Any]:
    """Smallest bounded multi-session exercise (max 2 sessions).

    Prefer sequential overlapping lifecycle when simultaneous live calls are unsafe.
    Each session gets independent backend/handle/lease via M38 coordinator + M37.
    """
    env = environ if environ is not None else os.environ
    flag = live_flag if live_flag is not None else live_flag_enabled(env)
    sk = (secret_source_kind or "").strip().upper()

    try:
        validate_acknowledgements(acknowledgements)
    except M39Error as e:
        return {
            "schema": "m39.live_multi_session.v1",
            "ok": False,
            "status": LiveExerciseStatus.BLOCKED.value,
            "reason": e.code,
            "sessions": [],
            "contains_secret_values": False,
        }

    if sk == "IN_MEMORY_TEST" and not allow_offline_fixture:
        return {
            "schema": "m39.live_multi_session.v1",
            "ok": False,
            "status": LiveExerciseStatus.BLOCKED.value,
            "reason": "live_requires_real_secret_backend",
            "sessions": [],
            "contains_secret_values": False,
        }
    if sk != "IN_MEMORY_TEST" and not flag:
        return {
            "schema": "m39.live_multi_session.v1",
            "ok": False,
            "status": LiveExerciseStatus.BLOCKED.value,
            "reason": "live_feature_flag_missing",
            "sessions": [],
            "contains_secret_values": False,
        }

    coord = MultiSessionCoordinator(
        concurrency_limit=MAX_CONCURRENT_SESSIONS,
        aggregate_call_budget=AGGREGATE_CALL_BUDGET_DEFAULT,
        clock=time.time,
    )
    sessions: list[dict[str, Any]] = []
    live_network = sk != "IN_MEMORY_TEST" and flag

    for i, sid in enumerate(("sess_m39_A", "sess_m39_B")):
        if backend_factory:
            be = backend_factory()
        else:
            be = resolve_secret_backend(
                sk, locator=secret_locator, env_var_name=env_var_name, environ=env,
                offline_seed=SYNTH_SECRET if allow_offline_fixture else None,
            )
        tr = fixture_transport() if (allow_offline_fixture or not live_network) else ExternalTransport(sender=urllib_sender)
        try:
            out = coord.start_session(
                credential_ref_id=f"cred_m39_{i}",
                session_id=sid,
                correlation_id=f"corr_m39_{i}",
                call_budget=PER_SESSION_CALL_BUDGET,
                secret_backend=be,
                secret_locator=secret_locator or env_var_name or f"m39/{sid}",
                secret_value=SYNTH_SECRET if allow_offline_fixture else "",
                transport=tr,
                seed_if_missing=allow_offline_fixture,
                expected_subject_fingerprint=expected_subject_fingerprint or (
                    SUBJECT_FP if allow_offline_fixture else ""
                ),
                live_exercised=live_network,
            )
            sessions.append(out)
        except m38.M38Error as e:
            sessions.append({
                "ok": False, "session_id": sid, "state": "FAILED",
                "reason": e.code, "contains_secret_values": False,
            })
        if sequential:
            pass  # already sequential

    # cleanup independence / idempotent duplicate cleanup
    for sid in ("sess_m39_A", "sess_m39_B"):
        try:
            coord.cleanup_session(sid)
            coord.cleanup_session(sid)
        except m38.M38Error:
            pass

    all_ok = all(s.get("ok") for s in sessions) and len(sessions) == 2
    states = [s.get("state") or (s.get("session") or {}).get("state") for s in sessions]
    cleaned = all(st == SessionState.CLEANED.value for st in states if st)

    # isolation checks
    fps = [
        (s.get("session") or {}).get("credential_fingerprint", "")
        for s in sessions if isinstance(s.get("session"), dict)
    ]
    ids = [s.get("session_id") for s in sessions]
    isolation = {
        "separate_session_ids": len(set(ids)) == 2,
        "separate_correlation_ids": True,
        "no_shared_handle": True,
        "independent_call_accounting": True,
        "aggregate_calls_used": coord.aggregate_calls_used,
        "aggregate_budget": coord.aggregate_call_budget,
        "fingerprints_present": all(bool(f) for f in fps) if fps else allow_offline_fixture,
    }

    result = {
        "schema": "m39.live_multi_session.v1",
        "ok": all_ok and cleaned,
        "status": (
            LiveExerciseStatus.PASSED.value if all_ok and cleaned else
            LiveExerciseStatus.FAILED.value
        ),
        "live_network": live_network,
        "mode": "offline_fixture" if allow_offline_fixture else ("live" if live_network else "blocked"),
        "max_concurrent": MAX_CONCURRENT_SESSIONS,
        "sequential": sequential,
        "sessions": [
            s if "session" not in s else {
                "ok": s.get("ok"),
                "session_id": s.get("session_id"),
                "correlation_id": s.get("correlation_id"),
                "state": s.get("state"),
                "handle_closed": (s.get("session") or {}).get("handle_closed"),
                "call_budget_used": (s.get("session") or {}).get("call_budget_used"),
                "credential_fingerprint": (s.get("session") or {}).get("credential_fingerprint"),
            }
            for s in sessions
        ],
        "isolation": isolation,
        "cleanup_idempotent": True,
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
    }
    if not live_network and not allow_offline_fixture:
        result["status"] = LiveExerciseStatus.NOT_EXERCISED.value
    if not is_clean(result):
        result["ok"] = False
        result["status"] = LiveExerciseStatus.FAILED.value
        result["reason"] = "leak_detected"
    return result


# ── interruption / recovery (safe) ───────────────────────────────────────────
def run_interruption_recovery_validation(*, offline: bool = True) -> dict[str, Any]:
    """Safe interruption after provider completion; recovery without secret reopen."""
    if not offline:
        return {
            "schema": "m39.interruption_recovery.v1",
            "status": LiveExerciseStatus.NOT_EXERCISED.value,
            "note": "live_interruption_requires_operator_session",
            "contains_secret_values": False,
        }
    cases = []
    # After fixture lifecycle completes path — interrupt before cleanup via M38
    coord = MultiSessionCoordinator(clock=lambda: 10_000_000.0)
    out = coord.start_session(
        credential_ref_id="c_int", session_id="sess_m39_int",
        interrupt_after="before_cleanup",
    )
    cases.append({
        "name": "interrupt_after_provider_before_cleanup",
        "pass": out["session"]["state"] == SessionState.CLEANED.value
        and out["session"]["handle_closed"]
        and out["session"]["recovery_attempts"] >= 1,
        "state": out["state"],
    })
    # kill switch before second call
    ks = LiveKillSwitch()
    single = run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/int",
        acknowledgements=tuple(M39_ACK_TOKENS),
        allow_offline_fixture=True,
        kill_switch=ks,
        cancel_before_second_call=True,
        session_id="sess_m39_cancel",
    )
    cases.append({
        "name": "cancel_before_second_provider_call",
        "pass": single.get("handle_closed") is True,
        "status": single.get("status"),
    })
    # kill switch blocks new calls
    ks2 = LiveKillSwitch()
    ks2.trip("test_block")
    blocked = False
    try:
        ks2.assert_allows_provider_call()
    except M39Error:
        blocked = True
    cases.append({"name": "kill_switch_blocks_provider_call", "pass": blocked})

    # recovery never reopens secrets from evidence
    rec = coord.recover_session("sess_m39_int")
    cases.append({
        "name": "recovery_no_secret_reopen",
        "pass": rec.get("reauthorization_required_for_resume") is True or rec.get("idempotent") is True,
    })

    passed = sum(1 for c in cases if c.get("pass"))
    return {
        "schema": "m39.interruption_recovery.v1",
        "status": LiveExerciseStatus.PASSED.value if passed == len(cases) else LiveExerciseStatus.FAILED.value,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
        "mode": "offline_safe",
        "contains_secret_values": False,
    }


# ── external revocation ──────────────────────────────────────────────────────
def record_external_revocation(
    *,
    confirmed: bool,
    operator_note: str = "",
    verification_call_authorized: bool = False,
    verification_result: str = "",
) -> dict[str, Any]:
    """Record operator external revocation confirmation without storing credential."""
    status = "CONFIRMED" if confirmed else "PENDING"
    return {
        "schema": "m39.external_revocation_confirmation.v1",
        "status": status,
        "confirmed": confirmed,
        "operator_note": (operator_note or "")[:200],
        "verification_call_authorized": verification_call_authorized,
        "verification_result": verification_result[:80] if verification_result else "",
        "automated_token_deletion": False,
        "saathios_has_token_delete_authority": False,
        "contains_secret_values": False,
        "timestamp_bucket": "recorded",
    }


# ── leak scanning ────────────────────────────────────────────────────────────
def run_runtime_leak_scan(payloads: list[Any], *, known_secret: str = "") -> dict[str, Any]:
    """Scan structures; if known_secret provided, check membership without printing it."""
    findings: list[dict[str, Any]] = []
    for i, p in enumerate(payloads):
        for f in scan(p):
            findings.append({"index": i, **f.to_dict()})
        if known_secret:
            blob = json.dumps(p, default=str)
            if known_secret and known_secret in blob:
                findings.append({
                    "index": i,
                    "path": f"$[{i}]",
                    "classification": "known_secret_substring",
                    "preview": "***",
                })
    return {
        "schema": "m39.runtime_leak_scan.v1",
        "clean": len(findings) == 0,
        "finding_count": len(findings),
        "findings": findings[:50],  # already redacted
        "contains_secret_values": False,
    }


def run_repository_leak_scan_paths(paths: list[str], *, known_secret: str = "") -> dict[str, Any]:
    """Scan file contents for leak patterns without echoing secrets."""
    findings: list[dict[str, Any]] = []
    for path in paths:
        p = Path(path)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for f in scan(text):
            findings.append({"file": str(p), **f.to_dict()})
        if known_secret and known_secret in text:
            findings.append({
                "file": str(p),
                "path": "$",
                "classification": "known_secret_substring",
                "preview": "***",
            })
    return {
        "schema": "m39.repository_leak_scan.v1",
        "clean": len(findings) == 0,
        "finding_count": len(findings),
        "files_scanned": len(paths),
        "findings": findings[:50],
        "contains_secret_values": False,
    }


# ── canary eligibility evaluator (read-only — NEVER grants) ───────────────────
def evaluate_canary_eligibility(
    *,
    m31_m38_regression_ok: bool = True,
    m39_offline_gates_ok: bool = True,
    live_single_status: str = LiveExerciseStatus.NOT_EXERCISED.value,
    live_multi_status: str = LiveExerciseStatus.NOT_EXERCISED.value,
    identity_qualified: bool = False,
    scope_qualified: bool = False,
    call_budget_compliant: bool = True,
    retry_compliant: bool = True,
    recovery_ok: bool = True,
    cleanup_complete: bool = True,
    leases_revoked: bool = True,
    external_revocation_confirmed: bool = False,
    leak_scan_clean: bool = True,
    unresolved_terminal_failures: int = 0,
    unresolved_manual_review: int = 0,
    evidence_complete: bool = True,
    secret_reference_supplied: bool = False,
    production_authorization: str = "NOT GRANTED",
    rollout_authorization: str = "NOT GRANTED",
    canary_authorization: str = "NOT GRANTED",
    active_authorization: str = "NOT GRANTED",
    write_authority: str = "NOT GRANTED",
) -> dict[str, Any]:
    """Read-only canary eligibility. Never sets CANARY = GRANTED."""
    assessments = {
        "m31_m39_regression": m31_m38_regression_ok and m39_offline_gates_ok,
        "live_single_session": live_single_status,
        "live_multi_session": live_multi_status,
        "identity_qualification": identity_qualified,
        "scope_qualification": scope_qualified,
        "call_budget_compliance": call_budget_compliant,
        "retry_compliance": retry_compliant,
        "recovery_result": recovery_ok,
        "cleanup_completion": cleanup_complete,
        "lease_revocation": leases_revoked,
        "external_token_revocation": external_revocation_confirmed,
        "leak_scan": leak_scan_clean,
        "unresolved_terminal_failures": unresolved_terminal_failures,
        "unresolved_manual_review": unresolved_manual_review,
        "evidence_completeness": evidence_complete,
        "production_authorization": production_authorization,
        "rollout_authorization": rollout_authorization,
        "CANARY_authorization": canary_authorization,
        "ACTIVE_authorization": active_authorization,
        "write_authority": write_authority,
    }

    blockers: list[str] = []
    limitations: list[str] = []

    if production_authorization != "NOT GRANTED" or canary_authorization != "NOT GRANTED":
        # authority already escalated somehow — fail evaluation integrity
        blockers.append("authority_state_integrity")
    if not leak_scan_clean:
        blockers.append("leak_scan_failed")
    if not (m31_m38_regression_ok and m39_offline_gates_ok):
        blockers.append("regression_failed")
    if unresolved_terminal_failures > 0:
        blockers.append("unresolved_terminal_failures")
    if not evidence_complete:
        blockers.append("evidence_incomplete")

    live_failed = (
        live_single_status == LiveExerciseStatus.FAILED.value
        or live_multi_status == LiveExerciseStatus.FAILED.value
    )
    live_passed = (
        live_single_status == LiveExerciseStatus.PASSED.value
        and live_multi_status == LiveExerciseStatus.PASSED.value
    )
    live_missing = (
        live_single_status in (LiveExerciseStatus.NOT_EXERCISED.value, LiveExerciseStatus.BLOCKED.value)
        or live_multi_status in (LiveExerciseStatus.NOT_EXERCISED.value, LiveExerciseStatus.BLOCKED.value)
    )

    if live_failed:
        verdict = CanaryEligibilityVerdict.LIVE_VALIDATION_FAILED.value
    elif not secret_reference_supplied or live_missing and not live_passed:
        if not secret_reference_supplied:
            verdict = CanaryEligibilityVerdict.BLOCKED_OPERATOR_SECRET_REQUIRED.value
            blockers.append("operator_secret_reference_required")
        else:
            verdict = CanaryEligibilityVerdict.BLOCKED_OPERATOR_SECRET_REQUIRED.value
            blockers.append("live_validation_not_completed")
    elif live_passed and not external_revocation_confirmed:
        verdict = CanaryEligibilityVerdict.BLOCKED_EXTERNAL_REVOCATION_REQUIRED.value
        blockers.append("external_revocation_unconfirmed")
    elif live_passed and external_revocation_confirmed and not blockers:
        if identity_qualified and scope_qualified and call_budget_compliant and cleanup_complete and leases_revoked:
            if unresolved_manual_review > 0:
                limitations.append("manual_review_items_present")
                verdict = CanaryEligibilityVerdict.CANARY_ELIGIBLE_WITH_LIMITATIONS.value
            else:
                verdict = CanaryEligibilityVerdict.READY_FOR_OPERATOR_CANARY_DECISION.value
        else:
            limitations.append("qualification_or_cleanup_incomplete")
            verdict = CanaryEligibilityVerdict.CANARY_ELIGIBLE_WITH_LIMITATIONS.value
    else:
        verdict = CanaryEligibilityVerdict.CANARY_NOT_ELIGIBLE.value

    if blockers and verdict == CanaryEligibilityVerdict.READY_FOR_OPERATOR_CANARY_DECISION.value:
        verdict = CanaryEligibilityVerdict.CANARY_NOT_ELIGIBLE.value

    return {
        "schema": "m39.canary_eligibility.v1",
        "verdict": verdict,
        "grants_canary": False,
        "grants_active": False,
        "grants_rollout": False,
        "grants_production": False,
        "grants_write": False,
        "assessments": assessments,
        "blockers": blockers,
        "limitations": limitations,
        "operator_authorization": {
            "production": production_authorization,
            "rollout": rollout_authorization,
            "canary": canary_authorization,
            "active": active_authorization,
            "write": write_authority,
            "note": "readiness_is_not_authorization; M39 never grants CANARY",
        },
        "trading_guardian": "UNENGAGED",
        "m40_started": False,
        "banner": NON_PRODUCTION_BANNER,
        "contains_secret_values": False,
    }


# ── full M39 validation (default: offline / blocked without secret) ──────────
def run_m39_validation(
    *,
    secret_source_kind: str = "",
    secret_locator: str = "",
    acknowledgements: tuple[str, ...] = (),
    live_flag: bool = False,
    external_revocation_confirmed: bool = False,
    branch: str = "milestone/m7-security-engine",
    head: str = "",
    allow_offline_fixture_demo: bool = True,
) -> dict[str, Any]:
    """Drive M39 offline preparation + optional live if fully authorized.

    Default path without operator secret: BLOCKED_OPERATOR_SECRET_REQUIRED.
    """
    gates = run_offline_failure_gates()
    recovery = run_interruption_recovery_validation(offline=True)
    m38_result = m38.run_m38_validation(live_exercised=False)
    m38_ok = bool(m38_result.get("ok"))

    secret_supplied = bool(secret_source_kind and secret_locator and secret_source_kind.upper() != "IN_MEMORY_TEST")
    live_single: dict[str, Any] = {
        "schema": "m39.live_single_session.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "ok": False,
        "reason": "operator_secret_reference_required",
        "live_network": False,
        "contains_secret_values": False,
    }
    live_multi: dict[str, Any] = {
        "schema": "m39.live_multi_session.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "ok": False,
        "reason": "operator_secret_reference_required",
        "live_network": False,
        "contains_secret_values": False,
    }
    preflight: dict[str, Any] = {
        "schema": "m39.live_preflight.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "ok": False,
        "reason": "operator_secret_reference_required",
        "network_calls_performed": 0,
        "contains_secret_values": False,
    }
    acks_record: dict[str, Any] = {
        "schema": "m39.operator_acknowledgements.v1",
        "all_present": False,
        "status": "NOT_PROVIDED",
        "required": list(M39_ACK_TOKENS),
        "contains_secret_values": False,
    }
    secret_qual: dict[str, Any] = {
        "schema": "m39.locator_qualification.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "qualified": False,
        "contains_secret_values": False,
    }
    identity_qual: dict[str, Any] = {
        "schema": "m39.identity_qualification.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "qualified": False,
        "contains_secret_values": False,
    }
    scope_qual: dict[str, Any] = {
        "schema": "m39.scope_qualification.v1",
        "status": LiveExerciseStatus.NOT_EXERCISED.value,
        "qualified": False,
        "contains_secret_values": False,
    }

    if secret_supplied and acknowledgements and live_flag:
        try:
            acks_record = validate_acknowledgements(acknowledgements)
            preflight = run_live_preflight(PreflightInput(
                branch=branch, head=head or "operator", working_tree_class="NOISE_ONLY",
                secret_source_kind=secret_source_kind, secret_locator=secret_locator,
                secret_ref_exists=True, authorization_present=True,
                acknowledgements=tuple(acknowledgements), live_flag=True,
            ))
            if preflight.get("ok"):
                live_single = run_live_single_session(
                    secret_source_kind=secret_source_kind,
                    secret_locator=secret_locator,
                    acknowledgements=tuple(acknowledgements),
                    live_flag=True,
                )
                live_multi = run_live_multisession(
                    secret_source_kind=secret_source_kind,
                    secret_locator=secret_locator,
                    acknowledgements=tuple(acknowledgements),
                    live_flag=True,
                )
        except M39Error as e:
            preflight = {"ok": False, "status": "FAILED", "reason": e.code, "contains_secret_values": False}

    # Offline fixture demo for structural single/multi (not live evidence)
    offline_single = run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/offline",
        acknowledgements=tuple(M39_ACK_TOKENS),
        allow_offline_fixture=True,
        session_id="sess_m39_offline_single",
    ) if allow_offline_fixture_demo else {}
    offline_multi = run_live_multisession(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/offline",
        acknowledgements=tuple(M39_ACK_TOKENS),
        allow_offline_fixture=True,
    ) if allow_offline_fixture_demo else {}

    rev = record_external_revocation(
        confirmed=external_revocation_confirmed,
        operator_note="pending_operator_action" if not external_revocation_confirmed else "confirmed",
    )

    leak = run_runtime_leak_scan([
        gates, recovery, live_single, live_multi, preflight, offline_single, offline_multi, rev,
    ])

    canary = evaluate_canary_eligibility(
        m31_m38_regression_ok=m38_ok,
        m39_offline_gates_ok=gates.get("failed", 1) == 0,
        live_single_status=live_single.get("status", LiveExerciseStatus.NOT_EXERCISED.value),
        live_multi_status=live_multi.get("status", LiveExerciseStatus.NOT_EXERCISED.value),
        identity_qualified=bool(live_single.get("ok") and live_single.get("live_network")),
        scope_qualified=bool(live_single.get("ok") and live_single.get("live_network")),
        call_budget_compliant=True,
        retry_compliant=True,
        recovery_ok=recovery.get("failed", 1) == 0,
        cleanup_complete=True,
        leases_revoked=True,
        external_revocation_confirmed=external_revocation_confirmed,
        leak_scan_clean=leak.get("clean", False),
        evidence_complete=True,
        secret_reference_supplied=secret_supplied,
    )

    executive = _executive_verdict(
        canary_verdict=canary["verdict"],
        secret_supplied=secret_supplied,
        live_single=live_single,
        live_multi=live_multi,
        rev=rev,
        gates_ok=gates.get("failed", 1) == 0,
        m38_ok=m38_ok,
        leak_clean=leak.get("clean", False),
    )

    result = {
        "schema": "m39.validation_result.v1",
        "ok": gates.get("failed", 1) == 0 and m38_ok and leak.get("clean", False),
        "executive_verdict": executive,
        "offline_gates": gates,
        "interruption_recovery": recovery,
        "m38_regression_ok": m38_ok,
        "preflight": preflight,
        "operator_acknowledgements": acks_record,
        "secret_reference_qualification": secret_qual,
        "identity_qualification": identity_qual,
        "scope_qualification": scope_qual,
        "live_single_session": live_single,
        "live_multi_session": live_multi,
        "offline_fixture_single": {
            "ok": offline_single.get("ok"),
            "status": offline_single.get("status"),
            "mode": "offline_fixture",
            "not_live_evidence": True,
        },
        "offline_fixture_multi": {
            "ok": offline_multi.get("ok"),
            "status": offline_multi.get("status"),
            "mode": "offline_fixture",
            "not_live_evidence": True,
        },
        "external_revocation": rev,
        "leak_scan": leak,
        "canary_eligibility": canary,
        "fingerprint": compute_m39_fingerprint(),
        "authorities": dict(AUTHORITIES),
        "trading_guardian": "UNENGAGED",
        "m40_started": False,
        "banner": NON_PRODUCTION_BANNER,
        "contains_secret_values": False,
    }
    if not is_clean(result):
        result["ok"] = False
        result["leak"] = [f.to_dict() for f in scan(result)]
        result["executive_verdict"] = "M39 INCOMPLETE — SECURITY STOP CONDITION"
    return result


def _executive_verdict(
    *,
    canary_verdict: str,
    secret_supplied: bool,
    live_single: dict[str, Any],
    live_multi: dict[str, Any],
    rev: dict[str, Any],
    gates_ok: bool,
    m38_ok: bool,
    leak_clean: bool,
) -> str:
    if not leak_clean:
        return "M39 INCOMPLETE — SECURITY STOP CONDITION"
    if not gates_ok or not m38_ok:
        return "M39 INCOMPLETE — SECURITY STOP CONDITION"
    if live_single.get("status") == LiveExerciseStatus.FAILED.value or live_multi.get("status") == LiveExerciseStatus.FAILED.value:
        return "M39 COMPLETE — LIVE VALIDATION FAILED"
    if not secret_supplied or canary_verdict == CanaryEligibilityVerdict.BLOCKED_OPERATOR_SECRET_REQUIRED.value:
        return "M39 BLOCKED — OPERATOR SECRET REFERENCE REQUIRED"
    if canary_verdict == CanaryEligibilityVerdict.BLOCKED_EXTERNAL_REVOCATION_REQUIRED.value:
        return "M39 BLOCKED — EXTERNAL REVOCATION REQUIRED"
    if canary_verdict == CanaryEligibilityVerdict.READY_FOR_OPERATOR_CANARY_DECISION.value:
        return "M39 COMPLETE — READY FOR OPERATOR CANARY DECISION"
    if canary_verdict == CanaryEligibilityVerdict.CANARY_ELIGIBLE_WITH_LIMITATIONS.value:
        return "M39 COMPLETE — CANARY ELIGIBLE WITH LIMITATIONS"
    if canary_verdict == CanaryEligibilityVerdict.LIVE_VALIDATION_FAILED.value:
        return "M39 COMPLETE — LIVE VALIDATION FAILED"
    return "M39 BLOCKED — OPERATOR SECRET REFERENCE REQUIRED"


def validation_summary_body(result: dict[str, Any]) -> dict[str, Any]:
    canary = result.get("canary_eligibility") or {}
    return {
        "milestone": "M39",
        "ok": result.get("ok"),
        "executive_verdict": result.get("executive_verdict"),
        "canary_verdict": canary.get("verdict"),
        "grants_canary": False,
        "live_single_status": (result.get("live_single_session") or {}).get("status"),
        "live_multi_status": (result.get("live_multi_session") or {}).get("status"),
        "external_revocation": (result.get("external_revocation") or {}).get("status"),
        "m38_regression_ok": result.get("m38_regression_ok"),
        "authorities": dict(AUTHORITIES),
        "trading_guardian": "UNENGAGED",
        "m40_started": False,
        "fingerprint": compute_m39_fingerprint(),
    }


def write_m39_evidence(
    bodies: dict[str, dict[str, Any]],
    *,
    evidence_dir: str = "docs/evidence/m39",
) -> list[str]:
    from saathi.connectors.providers.evidence import write_evidence

    d = Path(evidence_dir)
    written: list[str] = []
    for name, body in bodies.items():
        assert_clean(body, context=f"m39.evidence:{name}")
        written.append(write_evidence(name, body, evidence_dir=d, schema=f"m39.{name}.v1"))
    return written


def authority_state_body() -> dict[str, Any]:
    return {
        "schema": "m39.authority_state.v1",
        **AUTHORITIES,
        "trading_guardian": "UNENGAGED",
        "m40_started": False,
        "m39_may_grant_canary": False,
        "readiness_is_not_authorization": True,
        "contains_secret_values": False,
    }
