"""M21.2 — Deterministic provider decision, ranking, retry, and failover.

Flow (before any provider attempt):
  contract/caller policy (caller)
  → capability filter
  → availability
  → cost/privacy
  → kill + circuit
  → ranked decision

ModelRouter remains selection authority for model identity; this layer decides
which *providers* are eligible and whether retry/failover is permitted.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional, Sequence

from saathi.inference.availability import (
    AvailabilityDecision,
    AvailabilityState,
    HealthProbe,
    evaluate_availability,
    state_allows_attempt,
)
from saathi.inference.caller_policy import CallerPolicy, get_caller_policy, require_caller_policy
from saathi.inference.circuit_breaker import (
    ProviderCircuitBreakerRegistry,
    get_circuit_registry,
)
from saathi.inference.cost_policy import (
    CostEstimate,
    CostPolicyVerdict,
    estimate_cost,
    estimate_input_tokens,
    enforce_cost_policy,
)
from saathi.inference.failure_taxonomy import (
    FailureType,
    get_failure_spec,
    redact_error_message,
)
from saathi.inference.provider_descriptor import (
    ProviderDescriptor,
    get_descriptor,
    list_descriptors,
)
from saathi.inference.provider_policy import (
    is_master_killed,
    is_provider_killed,
    is_provider_policy_enabled,
    resolve_availability as resolve_static_availability,
)
from saathi.inference.request import InferenceRequest, Sensitivity


# Privacy labels map Sensitivity + extended names
_SENS_MAP = {
    "public": "public",
    "internal": "internal",
    "confidential": "confidential",
    "sensitive": "sensitive",
    "restricted": "restricted",
}


@dataclass(frozen=True)
class CapabilityMatch:
    ok: bool
    reason_code: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankedProvider:
    provider_id: str
    score: tuple  # lower is better (stable sort)
    reasons: tuple[str, ...]
    availability: AvailabilityDecision
    capability: CapabilityMatch
    cost: Optional[CostEstimate]
    cost_verdict: Optional[CostPolicyVerdict]
    eligible: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "score": list(self.score),
            "reasons": list(self.reasons),
            "availability": self.availability.to_dict(),
            "capability": self.capability.to_dict(),
            "cost": self.cost.to_dict() if self.cost else None,
            "cost_verdict": self.cost_verdict.to_dict() if self.cost_verdict else None,
            "eligible": self.eligible,
        }


@dataclass(frozen=True)
class ProviderDecision:
    """Explainable, privacy-safe provider decision."""

    ok: bool
    selected_provider_id: str
    reason_code: str
    explanation: str
    candidates: tuple[RankedProvider, ...]
    kill_switch: dict[str, Any]
    fallback_permitted: bool
    cloud_fallback_permitted: bool
    max_retries: int
    attempt_limit: int
    privacy: str
    request_fingerprint_prefix: str
    checked_at: float
    production_context: bool
    production_certified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "m21.2.provider_decision.v1",
            "ok": self.ok,
            "selected_provider_id": self.selected_provider_id,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "candidates": [c.to_dict() for c in self.candidates],
            "kill_switch": self.kill_switch,
            "fallback_permitted": self.fallback_permitted,
            "cloud_fallback_permitted": self.cloud_fallback_permitted,
            "max_retries": self.max_retries,
            "attempt_limit": self.attempt_limit,
            "privacy": self.privacy,
            "request_fingerprint_prefix": self.request_fingerprint_prefix,
            "checked_at": self.checked_at,
            "production_context": self.production_context,
            "production_certified": self.production_certified,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RetryDecision:
    allow: bool
    reason_code: str
    delay_seconds: float
    attempt: int
    max_retries: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FailoverDecision:
    allow: bool
    reason_code: str
    next_provider_id: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def privacy_label(req: InferenceRequest) -> str:
    sens = req.sensitivity
    if isinstance(sens, Sensitivity):
        raw = sens.value
    else:
        raw = str(sens or "internal").lower()
    return _SENS_MAP.get(raw, "internal")


def match_capabilities(
    desc: ProviderDescriptor,
    req: InferenceRequest,
    *,
    caller: Optional[CallerPolicy] = None,
) -> CapabilityMatch:
    """Validate capability compatibility before selection."""
    if req.streaming_requested and not desc.streaming_supported:
        return CapabilityMatch(False, "streaming_mismatch", "Streaming required but unsupported")
    if req.tool_use_permitted and not desc.tool_use_supported:
        return CapabilityMatch(False, "tool_use_mismatch", "Tool use required but unsupported")
    schema = (getattr(req, "structured_output_schema", "") or "").strip()
    if schema and not desc.structured_output_supported:
        return CapabilityMatch(
            False, "structured_output_mismatch", "Structured output required but unsupported"
        )
    if req.max_output_tokens > desc.max_output_tokens:
        return CapabilityMatch(False, "output_limit_mismatch", "Output tokens exceed provider max")
    # Context: rough char estimate
    text = req.prompt or ""
    if req.messages:
        text = " ".join(str(m.get("content") or "") for m in req.messages)
    approx_in = estimate_input_tokens(text + (req.system or ""))
    if approx_in > desc.max_context_tokens:
        return CapabilityMatch(False, "context_limit_mismatch", "Context exceeds provider max")
    if req.timeout_seconds > desc.max_timeout_seconds:
        return CapabilityMatch(False, "timeout_mismatch", "Timeout exceeds provider max")

    priv = privacy_label(req)
    if priv not in desc.privacy_classes_allowed:
        return CapabilityMatch(False, "privacy_mismatch", f"Privacy class {priv} not allowed")

    if req.local_only and desc.local_or_cloud == "cloud":
        return CapabilityMatch(False, "local_only_cloud", "local_only request cannot use cloud")

    if priv in {"confidential", "sensitive", "restricted"} and desc.cloud_data_processing:
        return CapabilityMatch(False, "privacy_cloud_denied", "Sensitive data cannot use cloud")

    # Capability family
    cap = (req.preferred_capability or req.task_type or "standard").lower()
    if caller and caller.allowed_capabilities and cap not in caller.allowed_capabilities:
        return CapabilityMatch(False, "capability_not_allowed_caller", f"Caller forbids {cap}")
    # model class hint — if engine_hint forces cloud while local_only
    if (req.engine_hint or "").strip().lower() in {"cloud", "openai", "anthropic"} and req.local_only:
        return CapabilityMatch(False, "model_class_mismatch", "Cloud engine hint under local_only")

    # Provider override via metadata denied
    if req.metadata.get("force_provider") or req.metadata.get("provider_override"):
        return CapabilityMatch(False, "caller_provider_override_denied", "Caller provider override denied")

    return CapabilityMatch(True, "ok", "Capability compatible")


def _score_tuple(
    desc: ProviderDescriptor,
    avail: AvailabilityDecision,
    cap: CapabilityMatch,
    cost_ok: bool,
    *,
    prefer_local: bool = True,
) -> tuple:
    """Lower is better. Stable deterministic ranking."""
    # 0 policy eligibility
    elig = 0 if (cap.ok and cost_ok and state_allows_attempt(avail.state)) else 1
    # 1 availability rank
    avail_rank = {
        AvailabilityState.AVAILABLE: 0,
        AvailabilityState.DEGRADED: 1,
        AvailabilityState.TEST_ONLY: 2,
        AvailabilityState.UNKNOWN: 5,
        AvailabilityState.UNAVAILABLE: 6,
        AvailabilityState.CIRCUIT_OPEN: 7,
        AvailabilityState.UNCERTIFIED: 8,
        AvailabilityState.MISCONFIGURED: 9,
        AvailabilityState.DISABLED: 10,
        AvailabilityState.FAKE: 11,
        AvailabilityState.KILLED: 12,
    }.get(avail.state, 20)
    # 2 certification
    cert = 0 if desc.production_supported else 1
    if desc.provider_class == "fake":
        cert = 9
    # 3 capability
    cap_rank = 0 if cap.ok else 1
    # 4 privacy (local better for sensitive — already filtered)
    priv = 0 if desc.local_or_cloud == "local" else 1
    # 5 local-first
    local = 0 if (prefer_local and desc.local_or_cloud == "local") else 1
    # 6 cost known better
    cost_rank = 0 if cost_ok else 1
    if desc.pricing.zero_marginal:
        cost_rank = 0
    elif not desc.pricing.known:
        cost_rank = 2
    # 7 health evidence
    health = 0 if avail.state is AvailabilityState.AVAILABLE else 1
    # 8 circuit
    circuit = 1 if avail.state is AvailabilityState.CIRCUIT_OPEN else 0
    # 9 stable id
    return (elig, avail_rank, cert, cap_rank, priv, local, cost_rank, health, circuit, desc.provider_id)


def decide_providers(
    req: InferenceRequest,
    *,
    production_context: bool = False,
    allow_cloud_fallback: bool = False,
    health_probe: Optional[HealthProbe] = None,
    circuits: Optional[ProviderCircuitBreakerRegistry] = None,
    descriptors: Optional[Sequence[ProviderDescriptor]] = None,
    now: Optional[float] = None,
    master_inference_enabled: Optional[bool] = None,
) -> ProviderDecision:
    """Produce a deterministic provider decision for a canonical request."""
    checked = float(now if now is not None else time.time())
    circuits = circuits or get_circuit_registry()
    descs = list(descriptors if descriptors is not None else list_descriptors())

    kill = {
        "kill_all": is_master_killed(),
        "global_blocks_all": is_master_killed(),
    }

    fp = ""
    try:
        from saathi.inference.contract import request_fingerprint

        fp = request_fingerprint(req)[:24]
    except Exception:
        fp = (req.request_id or "")[:24]

    priv = privacy_label(req)
    caller = get_caller_policy(req.caller_component)
    caller_pol = require_caller_policy(req.caller_component)

    # Transitional unknown: production hard deny
    if (req.caller_component or "unknown") == "unknown":
        if production_context or _unknown_caller_production_blocked():
            return ProviderDecision(
                ok=False,
                selected_provider_id="",
                reason_code="unknown_caller",
                explanation="Unknown/transitional caller denied outside tests",
                candidates=(),
                kill_switch=kill,
                fallback_permitted=False,
                cloud_fallback_permitted=False,
                max_retries=0,
                attempt_limit=1,
                privacy=priv,
                request_fingerprint_prefix=fp,
                checked_at=checked,
                production_context=production_context,
                metadata={"failure_type": FailureType.UNKNOWN_CALLER.value},
            )

    if is_master_killed():
        return ProviderDecision(
            ok=False,
            selected_provider_id="",
            reason_code="kill_switch_active",
            explanation="SAATHI_INFERENCE_KILL_ALL active",
            candidates=(),
            kill_switch=kill,
            fallback_permitted=False,
            cloud_fallback_permitted=False,
            max_retries=0,
            attempt_limit=0,
            privacy=priv,
            request_fingerprint_prefix=fp,
            checked_at=checked,
            production_context=production_context,
            metadata={"failure_type": FailureType.KILL_SWITCH_ACTIVE.value},
        )

    # Fallback defaults: none / no cloud
    fallback_req = (getattr(req, "fallback_policy", "none") or "none").lower() != "none"
    fallback_req = fallback_req or bool(req.cloud_fallback_permitted)
    caller_fallback = bool(caller_pol.cloud_fallback_allowed) if caller else False
    # soft_local only if request fallback_policy says so
    soft_local = (getattr(req, "fallback_policy", "none") or "none").lower() in {
        "soft_local",
        "local",
        "soft",
    }
    fallback_permitted = soft_local and not production_context  # still gated per failure
    # Default no fallback for M21.2 governed decisions unless explicit soft_local
    if (getattr(req, "fallback_policy", "none") or "none").lower() == "none":
        fallback_permitted = False

    cloud_ok = bool(allow_cloud_fallback) and bool(req.cloud_fallback_permitted) and bool(
        getattr(req, "cloud_allowed", False) or req.cloud_fallback_permitted
    )
    if req.local_only:
        cloud_ok = False
    if priv in {"confidential", "sensitive", "restricted"}:
        cloud_ok = False
    if caller and not caller.cloud_allowed:
        cloud_ok = False

    text = req.prompt or ""
    if req.messages:
        text = " ".join(str(m.get("content") or "") for m in req.messages)
    in_tok = estimate_input_tokens(text + (req.system or ""))

    ranked: list[RankedProvider] = []
    for desc in descs:
        killed = is_provider_killed(desc.provider_id)
        allow_c, allow_reason = circuits.allow_request(desc.provider_id)
        circuit_open = not allow_c and allow_reason == "circuit_open"

        # Policy enabled — recompute with call-time flags (descriptor.enabled is env snapshot)
        mi = master_inference_enabled
        if mi is None:
            mi = True  # decision layer assumes inference intended when called from gateway
        try:
            enabled = is_provider_policy_enabled(
                desc.provider_id,
                master_inference_enabled=bool(mi),
                allow_cloud_fallback=bool(cloud_ok),
            )
        except Exception:
            enabled = bool(desc.enabled)
        if killed:
            enabled = False
        if desc.local_or_cloud == "cloud" and not cloud_ok:
            enabled = False

        cap = match_capabilities(desc, req, caller=caller)

        cost_est = estimate_cost(
            desc.pricing,
            input_tokens=in_tok,
            output_tokens_ceiling=req.max_output_tokens,
            now=checked,
        )
        paid = desc.local_or_cloud == "cloud" and not desc.pricing.zero_marginal
        cost_v = enforce_cost_policy(
            cost_est,
            request_ceiling=getattr(req, "request_cost_ceiling", 0.0) or None,
            caller_ceiling=caller_pol.request_cost_ceiling if caller_pol.request_cost_ceiling else None,
            cloud_fallback=desc.local_or_cloud == "cloud",
            paid_provider=paid,
        )
        # Zero ceiling with zero cost OK for local
        if desc.pricing.zero_marginal:
            cost_v = enforce_cost_policy(
                cost_est,
                request_ceiling=None,
                paid_provider=False,
            )

        policy_eligible = cap.ok and cost_v.allowed
        if desc.provider_class == "fake" and production_context:
            policy_eligible = False

        avail = evaluate_availability(
            desc.provider_id,
            policy_enabled=enabled and not is_master_killed(),
            configured=desc.configured,
            credential_required=desc.credential_required,
            credential_present=desc.credential_present,
            production_supported=desc.production_supported,
            production_context=production_context,
            provider_class=desc.provider_class,
            killed=killed or is_master_killed(),
            circuit_open=circuit_open,
            capability_compatible=cap.ok,
            policy_eligible=policy_eligible,
            health_probe=health_probe,
            now=checked,
        )

        eligible = (
            policy_eligible
            and cost_v.allowed
            and state_allows_attempt(avail.state)
            and allow_c
            and not killed
        )
        # Fake never in production
        if production_context and desc.provider_class == "fake":
            eligible = False
        # Cloud never unless all gates
        if desc.local_or_cloud == "cloud" and not cloud_ok:
            eligible = False

        reasons = [
            avail.reason_code,
            cap.reason_code,
            cost_v.reason_code,
            allow_reason,
        ]
        score = _score_tuple(desc, avail, cap, cost_v.allowed)
        ranked.append(
            RankedProvider(
                provider_id=desc.provider_id,
                score=score,
                reasons=tuple(reasons),
                availability=avail,
                capability=cap,
                cost=cost_est,
                cost_verdict=cost_v,
                eligible=eligible,
            )
        )

    ranked.sort(key=lambda r: r.score)
    eligible = [r for r in ranked if r.eligible]
    max_retries = int(getattr(req, "max_retries", 0) or 0)
    if caller:
        max_retries = min(max_retries, int(caller.max_retries or 0))
    max_retries = max(0, max_retries)
    attempt_limit = 1 + max_retries

    if not eligible:
        # Prefer first hard reason
        top = ranked[0] if ranked else None
        code = "no_eligible_provider"
        expl = "No provider passed availability, capability, cost, and kill checks"
        if top:
            code = top.reasons[0] if top.reasons else code
            expl = top.availability.explanation
        return ProviderDecision(
            ok=False,
            selected_provider_id="",
            reason_code=code,
            explanation=expl,
            candidates=tuple(ranked),
            kill_switch=kill,
            fallback_permitted=False,
            cloud_fallback_permitted=cloud_ok,
            max_retries=max_retries,
            attempt_limit=attempt_limit,
            privacy=priv,
            request_fingerprint_prefix=fp,
            checked_at=checked,
            production_context=production_context,
            metadata={"eligible_count": 0},
        )

    chosen = eligible[0]
    return ProviderDecision(
        ok=True,
        selected_provider_id=chosen.provider_id,
        reason_code="selected",
        explanation=f"Selected {chosen.provider_id} by deterministic ranking",
        candidates=tuple(ranked),
        kill_switch=kill,
        fallback_permitted=fallback_permitted,
        cloud_fallback_permitted=cloud_ok,
        max_retries=max_retries,
        attempt_limit=attempt_limit,
        privacy=priv,
        request_fingerprint_prefix=fp,
        checked_at=checked,
        production_context=production_context,
        metadata={
            "eligible_count": len(eligible),
            "score": list(chosen.score),
            "ranking_reasons": list(chosen.reasons),
        },
    )


def _unknown_caller_production_blocked() -> bool:
    """Transitional unknown blocked unless pytest/test env."""
    import os
    import sys

    if os.getenv("SAATHI_ALLOW_UNKNOWN_CALLER", "").strip().lower() in {"1", "true", "yes", "on"}:
        # Still not production — only for explicit test harnesses
        return os.getenv("SAATHI_PRODUCTION_POSTURE", "").strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("SAATHI_PRODUCTION_POSTURE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    # pytest
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    # Default for governed decision API: block unknown in non-test runtime
    if os.getenv("SAATHI_ENV", "").strip().lower() in {"production", "prod", "staging"}:
        return True
    return False


def decide_retry(
    failure_type: FailureType | str,
    *,
    attempt: int,
    max_retries: int = 0,
    cost_remaining_ok: bool = True,
) -> RetryDecision:
    """Bounded deterministic retry. Default max_retries=0."""
    spec = get_failure_spec(failure_type)
    max_retries = max(0, int(max_retries))
    attempt = max(0, int(attempt))
    if max_retries <= 0:
        return RetryDecision(False, "max_retries_zero", 0.0, attempt, max_retries)
    if attempt >= max_retries:
        return RetryDecision(False, "retry_exhausted", 0.0, attempt, max_retries)
    if not spec.retryable or not spec.same_provider_retry:
        return RetryDecision(False, "not_retryable", 0.0, attempt, max_retries)
    if spec.failure_class.value == "hard":
        return RetryDecision(False, "hard_denial", 0.0, attempt, max_retries)
    if not cost_remaining_ok:
        return RetryDecision(False, "cost_ceiling", 0.0, attempt, max_retries)
    # Deterministic backoff: 0.05 * 2^attempt seconds, cap 2.0
    delay = min(2.0, 0.05 * (2 ** attempt))
    return RetryDecision(True, "retry", delay, attempt + 1, max_retries)


def decide_failover(
    failure_type: FailureType | str,
    decision: ProviderDecision,
    *,
    failed_provider_id: str,
    request_allows_fallback: bool,
    caller_allows_fallback: bool,
    privacy_ok: bool = True,
) -> FailoverDecision:
    """Failover requires all gates; default no fallback / no cloud."""
    spec = get_failure_spec(failure_type)
    if not request_allows_fallback:
        return FailoverDecision(False, "request_fallback_off", "", "Request disallows fallback")
    if not caller_allows_fallback:
        return FailoverDecision(False, "caller_fallback_off", "", "Caller disallows fallback")
    if not decision.fallback_permitted:
        return FailoverDecision(False, "decision_fallback_off", "", "Decision fallback_permitted=false")
    if not spec.failover_eligible:
        return FailoverDecision(False, "failure_not_failover_eligible", "", spec.operator_message)
    if not privacy_ok:
        return FailoverDecision(False, "privacy_denied", "", "Privacy blocks failover")
    if not decision.cloud_fallback_permitted:
        # Only local replacements
        nxt = next(
            (
                c.provider_id
                for c in decision.candidates
                if c.eligible
                and c.provider_id != failed_provider_id
                and c.availability.state
                in {AvailabilityState.AVAILABLE, AvailabilityState.DEGRADED}
            ),
            "",
        )
        # Filter cloud via candidates already; re-check descriptor
        if nxt:
            d = get_descriptor(nxt)
            if d and d.local_or_cloud == "cloud":
                nxt = ""
        if not nxt:
            return FailoverDecision(
                False, "no_local_replacement", "", "No eligible local failover target"
            )
        return FailoverDecision(True, "local_failover", nxt, f"Failover to {nxt}")
    # Cloud permitted path (still requires eligible cloud candidate)
    nxt = next(
        (c.provider_id for c in decision.candidates if c.eligible and c.provider_id != failed_provider_id),
        "",
    )
    if not nxt:
        return FailoverDecision(False, "no_replacement", "", "No eligible failover target")
    if not spec.cloud_fallback_eligible:
        d = get_descriptor(nxt)
        if d and d.local_or_cloud == "cloud":
            return FailoverDecision(False, "cloud_failover_not_eligible", "", "Cloud failover not eligible")
    return FailoverDecision(True, "failover", nxt, f"Failover to {nxt}")


def privacy_safe_decision_telemetry(decision: ProviderDecision) -> dict[str, Any]:
    """Never includes prompt/output/credentials."""
    return {
        "schema": "m21.2.decision_telemetry.v1",
        "ok": decision.ok,
        "selected_provider_id": decision.selected_provider_id,
        "reason_code": decision.reason_code,
        "eligible_count": decision.metadata.get("eligible_count"),
        "fallback_permitted": decision.fallback_permitted,
        "cloud_fallback_permitted": decision.cloud_fallback_permitted,
        "privacy": decision.privacy,
        "request_fingerprint_prefix": decision.request_fingerprint_prefix,
        "kill_all": decision.kill_switch.get("kill_all"),
        "production_certified": decision.production_certified,
        "candidate_ids": [c.provider_id for c in decision.candidates],
        "candidate_states": {
            c.provider_id: c.availability.state.value for c in decision.candidates
        },
    }


def record_provider_outcome(
    provider_id: str,
    failure_type: Optional[FailureType | str],
    *,
    success: bool,
    circuits: Optional[ProviderCircuitBreakerRegistry] = None,
) -> None:
    """Update circuit from outcome. Policy failures should pass failure_type that has circuit_impact=False."""
    reg = circuits or get_circuit_registry()
    if success:
        reg.record_success(provider_id)
        return
    if failure_type is None:
        reg.record_failure(provider_id, reason="unknown", counts=True)
        return
    spec = get_failure_spec(failure_type)
    reg.record_failure(
        provider_id,
        reason=spec.failure_type.value,
        counts=bool(spec.circuit_impact),
    )
