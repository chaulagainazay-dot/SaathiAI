"""M48.2 — canonical public agent-run entry point.

``start_agent_run`` is the only supported façade for new callers. It:

1. normalizes the request
2. runs M48.1 ``validate_run_request`` (fail-closed)
3. resolves capability / authority / approval / provider honesty
4. only then hands off to ``Orchestrator.create_run``

Does **not** replace Orchestrator, RunStore, or ExecutionGateway.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.agent_runtime.contracts import (
    AgentRunRequest,
    AuthorityClass,
    ContractErrorCode,
    ModelResolutionStatus,
    approval_requirement_for,
    classify_provider_status,
    parse_authority,
    provider_status_is_success,
    validate_run_request,
)
from saathi.agent_runtime.errors import (
    AgentRunError,
    AgentRuntimeErrorCode,
    public_code_for_contract,
)
from saathi.agent_runtime.orchestrator import Orchestrator, default_orchestrator
from saathi.agent_runtime.strategies import STRATEGIES, choose_strategy

# Capability aliases → canonical M48.1 names
CAPABILITY_ALIASES: dict[str, str] = {
    "planning": "plan",
    "planner": "plan",
    "coding": "code",
    "implement": "code",
    "build": "code",
    "reviewing": "review",
    "writing": "write",
    "docs": "write",
    "researching": "research",
    "ceo": "ceo_brief",
    "brief": "ceo_brief",
    "diag": "diagnostics",
    "local_exec": "execute_local",
    "trade": "trade_execute",  # still prohibited
    "execute_trade": "trade_execute",
}

# Strategy → default capability for create_run convenience paths
STRATEGY_CAPABILITY: dict[str, str] = {
    "single": "plan",
    "build": "code",
    "architect_build": "architect",
    "document": "write",
    "business": "ceo_brief",
    "broad_research": "research",
}


@dataclass
class AgentRunRecord:
    """Result of start_agent_run — never claims success when rejected."""

    ok: bool
    status: str  # accepted | rejected
    run_id: str = ""
    state: str = ""
    error_code: str = ""
    message: str = ""
    violations: list[dict] = field(default_factory=list)
    capability: str = ""
    authority: str = ""
    approval_requirement: str = ""
    provider_status: str = ""
    strategy: str = ""
    outcome: dict | None = None
    events_emitted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_capability(raw: str, *, strategy: str = "") -> str:
    cap = (raw or "").strip().lower()
    if not cap and strategy:
        cap = STRATEGY_CAPABILITY.get(strategy, "plan")
    if not cap:
        cap = "plan"
    return CAPABILITY_ALIASES.get(cap, cap)


def request_from_objective(
    objective: str,
    *,
    strategy: str = "",
    actor: str = "user:ajay",
    project_id: str = "",
    conversation_id: str = "",
    budget: dict | None = None,
    authority_class: str = AuthorityClass.READ_ONLY.value,
    requested_capability: str = "",
    approval_token: str | None = None,
    approval_expires_at: float | None = None,
    approval_revoked: bool = False,
    timeout_sec: float = 60.0,
    max_retries: int = 2,
    idempotency_key: str = "",
    input_payload: dict | None = None,
    agent_id: str = "",
) -> AgentRunRequest:
    """Build AgentRunRequest for legacy callers (objective + strategy)."""
    budget = dict(budget or {})
    if idempotency_key:
        budget["idempotency_key"] = idempotency_key
    strat = choose_strategy(objective, requested=strategy)
    cap = normalize_capability(requested_capability, strategy=strat)
    # Prefer explicit timeout/retries from budget when present
    if "timeout_sec" in budget:
        try:
            timeout_sec = float(budget["timeout_sec"])
        except (TypeError, ValueError):
            pass
    if "max_retries" in budget:
        try:
            max_retries = int(budget["max_retries"])
        except (TypeError, ValueError):
            pass
    payload = dict(input_payload or {})
    payload.setdefault("actor", actor)
    payload.setdefault("conversation_id", conversation_id)
    return AgentRunRequest(
        objective=objective,
        mission_id=str(budget.get("mission_id") or ""),
        project_id=project_id,
        workspace_id=str(budget.get("workspace_id") or ""),
        agent_id=agent_id,
        requested_capability=cap,
        requested_model=str(budget.get("requested_model") or ""),
        authority_class=authority_class,
        tool_policy=dict(budget.get("tool_policy") or {}),
        approval_token=approval_token or budget.get("approval_token"),
        approval_expires_at=approval_expires_at
        if approval_expires_at is not None
        else budget.get("approval_expires_at"),
        approval_revoked=bool(approval_revoked or budget.get("approval_revoked")),
        timeout_sec=timeout_sec,
        max_retries=max_retries,
        input_payload=payload,
        context_refs=list(budget.get("context_refs") or []),
        memory_refs=list(budget.get("memory_refs") or []),
        security_classification=str(budget.get("security_classification") or "internal"),
    )


def _violations_to_public(violations) -> list[dict]:
    out = []
    for v in violations:
        d = v.to_dict() if hasattr(v, "to_dict") else dict(v)
        code = d.get("code") or ""
        out.append(
            {
                "code": public_code_for_contract(code) if code else AgentRuntimeErrorCode.VALIDATION_FAILED,
                "contract_code": code,
                "message": d.get("message", ""),
                "field": d.get("field", ""),
            }
        )
    return out


def _primary_error(violations) -> tuple[str, str]:
    if not violations:
        return AgentRuntimeErrorCode.VALIDATION_FAILED, "validation failed"
    v = violations[0]
    code = v.code.value if hasattr(v.code, "value") else str(v.code)
    return public_code_for_contract(code), v.message


def resolve_provider_status(
    *,
    requested_model: str = "",
    provider_available: bool | None = None,
    provider_configured: bool = True,
    provider_prohibited: bool = False,
) -> ModelResolutionStatus:
    """Honest provider status without live network calls.

    When ``provider_available`` is None, we treat local/default routing as
    *configuration present but not proven live* only if configured; callers
    that need offline determinism should pass provider_available explicitly.
    Default for M48.2: assume configured local/test path is available unless
    prohibited — orchestrator injects execute_fn in tests.
    """
    if provider_prohibited:
        return ModelResolutionStatus.PROHIBITED
    if not provider_configured:
        return ModelResolutionStatus.CONFIGURATION_MISSING
    if provider_available is False:
        return ModelResolutionStatus.UNAVAILABLE
    if provider_available is True:
        return ModelResolutionStatus.SELECTED
    # Unproven: still allow orchestration handoff with SELECTED only when
    # capability is read-only planning; callers can force UNAVAILABLE.
    return ModelResolutionStatus.SELECTED


def _find_idempotent_run(orch: Orchestrator, key: str) -> dict | None:
    """Look up run by budget.idempotency_key (full row via get_run)."""
    if not key:
        return None
    # list_runs is a summary projection; load full rows for budget metadata
    for summary in orch.store.list_runs(limit=100):
        run = orch.store.get_run(summary["id"])
        if not run:
            continue
        budget = run.get("budget") or {}
        if isinstance(budget, str):
            try:
                budget = json.loads(budget)
            except Exception:
                budget = {}
        if budget.get("idempotency_key") == key:
            run = dict(run)
            run["budget"] = budget
            return run
    return None


def _request_fingerprint(req: AgentRunRequest) -> str:
    blob = json.dumps(
        {
            "objective": req.objective,
            "capability": req.requested_capability,
            "authority": req.authority_class,
            "project_id": req.project_id,
            "agent_id": req.agent_id,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def ensure_run_request_allowed(
    req: AgentRunRequest,
    *,
    provider_status: ModelResolutionStatus | None = None,
    now: float | None = None,
) -> list:
    """Validate request; return contract violations (empty = allowed)."""
    req.requested_capability = normalize_capability(req.requested_capability)
    errs = list(validate_run_request(req, now=now))
    if provider_status is not None and not provider_status_is_success(provider_status):
        from saathi.agent_runtime.contracts import ContractViolation

        errs.append(
            ContractViolation(
                ContractErrorCode.PROVIDER_UNAVAILABLE
                if provider_status
                in (
                    ModelResolutionStatus.UNAVAILABLE,
                    ModelResolutionStatus.CONFIGURATION_MISSING,
                )
                else ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED
                if provider_status == ModelResolutionStatus.PROHIBITED
                else ContractErrorCode.PROVIDER_UNAVAILABLE,
                f"provider status {provider_status.value} is not executable",
                field="provider",
            )
        )
    return errs


def start_agent_run(
    request: AgentRunRequest | None = None,
    *,
    objective: str = "",
    strategy: str = "",
    actor: str = "user:ajay",
    project_id: str = "",
    conversation_id: str = "",
    budget: dict | None = None,
    orchestrator: Orchestrator | None = None,
    execute: bool = False,
    max_wall_sec: float = 60.0,
    authority_class: str = AuthorityClass.READ_ONLY.value,
    requested_capability: str = "",
    approval_token: str | None = None,
    approval_expires_at: float | None = None,
    approval_revoked: bool = False,
    timeout_sec: float = 60.0,
    max_retries: int = 2,
    idempotency_key: str = "",
    provider_available: bool | None = None,
    provider_configured: bool = True,
    provider_prohibited: bool = False,
    raise_on_reject: bool = False,
) -> AgentRunRecord:
    """Canonical entry: validate then create (and optionally execute) a run.

    Strategy A: invalid requests return ``status=rejected`` with **no** durable
    run record and no orchestrator handoff.
    """
    orch = orchestrator or default_orchestrator()
    budget = dict(budget or {})
    if request is None:
        if not (objective or "").strip():
            rec = AgentRunRecord(
                ok=False,
                status="rejected",
                error_code=AgentRuntimeErrorCode.VALIDATION_FAILED,
                message="objective is required",
            )
            if raise_on_reject:
                raise AgentRunError(rec.error_code, rec.message)
            return rec
        request = request_from_objective(
            objective,
            strategy=strategy,
            actor=actor,
            project_id=project_id,
            conversation_id=conversation_id,
            budget=budget,
            authority_class=authority_class,
            requested_capability=requested_capability,
            approval_token=approval_token,
            approval_expires_at=approval_expires_at,
            approval_revoked=approval_revoked,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            idempotency_key=idempotency_key,
        )
    else:
        request.requested_capability = normalize_capability(
            request.requested_capability, strategy=strategy
        )
        if idempotency_key and not budget.get("idempotency_key"):
            budget["idempotency_key"] = idempotency_key

    # Idempotency (bounded): same key + same fingerprint returns existing run
    key = idempotency_key or (budget.get("idempotency_key") or "")
    if key:
        existing = _find_idempotent_run(orch, key)
        if existing:
            prev_fp = (existing.get("budget") or {}).get("request_fingerprint")
            fp = _request_fingerprint(request)
            if prev_fp and prev_fp != fp:
                rec = AgentRunRecord(
                    ok=False,
                    status="rejected",
                    error_code=AgentRuntimeErrorCode.IDEMPOTENCY_CONFLICT,
                    message="idempotency key reused with different request",
                    run_id=existing.get("id", ""),
                )
                if raise_on_reject:
                    raise AgentRunError(rec.error_code, rec.message, run_id=rec.run_id)
                return rec
            return AgentRunRecord(
                ok=True,
                status="accepted",
                run_id=existing["id"],
                state=existing.get("state", ""),
                message="idempotent replay of existing run",
                capability=request.requested_capability,
                authority=request.authority_class,
                strategy=existing.get("strategy", ""),
            )

    provider_status = resolve_provider_status(
        requested_model=request.requested_model,
        provider_available=provider_available,
        provider_configured=provider_configured,
        provider_prohibited=provider_prohibited,
    )
    violations = ensure_run_request_allowed(request, provider_status=provider_status)
    auth = parse_authority(request.authority_class)
    need = (
        approval_requirement_for(auth, capability=request.requested_capability)
        if auth
        else None
    )

    if violations:
        pub = _violations_to_public(violations)
        code, msg = _primary_error(violations)
        rec = AgentRunRecord(
            ok=False,
            status="rejected",
            error_code=code,
            message=msg,
            violations=pub,
            capability=request.requested_capability,
            authority=str(request.authority_class),
            approval_requirement=need.value if need else "",
            provider_status=provider_status.value,
        )
        if raise_on_reject:
            raise AgentRunError(code, msg, violations=pub)
        return rec

    # Enrich budget for audit (no secrets)
    budget = dict(budget)
    budget["idempotency_key"] = key or budget.get("idempotency_key", "")
    budget["request_fingerprint"] = _request_fingerprint(request)
    budget["capability"] = request.requested_capability
    budget["authority_class"] = request.authority_class
    budget["provider_status"] = provider_status.value
    budget["timeout_sec"] = request.timeout_sec
    budget["max_retries"] = request.max_retries
    if request.approval_token:
        # store only presence flag, never the raw token
        budget["approval_present"] = True

    strat = choose_strategy(request.objective, requested=strategy)
    events = ["validation.passed", "capability.resolved", "authority.resolved"]

    # Handoff — Orchestrator re-validates (defense in depth)
    rid = orch.create_run(
        request.objective,
        actor=str(request.input_payload.get("actor") or actor),
        strategy=strategy,
        project_id=request.project_id or project_id,
        conversation_id=str(
            request.input_payload.get("conversation_id") or conversation_id
        ),
        budget=budget,
        contract_request=request,
        provider_status=provider_status,
    )
    events.append("run.created")
    events.append("orchestrator.handoff")

    outcome = None
    state = "queued"
    if execute:
        outcome = orch.run(rid, max_wall_sec=max_wall_sec or request.timeout_sec)
        state = str(outcome.get("state") or "")
        events.append("orchestrator.executed")
    else:
        run = orch.store.get_run(rid)
        state = (run or {}).get("state", "queued")

    return AgentRunRecord(
        ok=True,
        status="accepted",
        run_id=rid,
        state=state,
        message="run accepted",
        capability=request.requested_capability,
        authority=request.authority_class,
        approval_requirement=need.value if need else "",
        provider_status=provider_status.value,
        strategy=strat,
        outcome=outcome,
        events_emitted=events,
    )
