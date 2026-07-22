"""M32 — Provider execution eligibility (additional layer; composes, never replaces).

Execution eligibility =
    platform production certification (M25)
  + connector certification (M30)
  + provider adapter verification (M32)
  + provider configuration readiness (M32)
  + account and credential readiness (M31, where applicable)
  + rollout
  + approval

Every layer stays distinct and every read is NON-mutating (M31 correction
preserved): resolving eligibility never refreshes or mutates the certification or
verification stores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.connectors.providers.config import ProviderConfig, validate_config
from saathi.connectors.providers.models import (
    ExecutionMode,
    M32_PROHIBITED_MODES,
    ProviderSideEffectClass,
    provider_is_prohibited,
)
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    resolve_provider_verification,
)

_OVERRIDE_KEYS = frozenset({
    "force_verified", "bypass_verification", "provider_verified",
    "skip_provider_check", "provider_override", "force_provider",
    "force_certified", "bypass_certification",
})


def caller_cannot_override_provider(metadata: Optional[dict[str, Any]]) -> bool:
    if not metadata:
        return False
    return any(str(k).lower() in _OVERRIDE_KEYS for k in metadata)


@dataclass
class ProviderEligibilityDecision:
    allowed: bool
    provider_id: str
    connector_id: str
    reason: str = "ok"
    mode: str = ExecutionMode.SIMULATION.value
    layers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_execution_eligibility(
    *,
    identity: Any,
    config: ProviderConfig,
    connector_manifest: Any = None,
    mode: str = ExecutionMode.SIMULATION.value,
    production_certified: bool = True,
    connector_certified: bool = True,
    account_ready: bool = True,
    credential_ready: bool = True,
    approval_valid: bool = True,
    rollout_permits_production: bool = False,
    verification_store: Optional[ProviderVerificationStore] = None,
    caller_metadata: Optional[dict[str, Any]] = None,
    test_corpus_id: str = "m32.corpus.v1",
    simulator_version: str = "",
) -> ProviderEligibilityDecision:
    """Compose all eligibility layers. Fail closed on any denial. Never mutates stores."""
    pid = getattr(identity, "provider_id", "")
    cid = getattr(identity, "connector_id", "")
    layers: dict[str, Any] = {}

    # caller may never forge eligibility
    if caller_cannot_override_provider(caller_metadata):
        return ProviderEligibilityDecision(False, pid, cid, reason="caller_override_rejected", mode=mode, layers=layers)

    # prohibited provider fails closed regardless of other layers
    reason = provider_is_prohibited(pid, capabilities=getattr(identity, "capabilities", ()))
    if reason:
        return ProviderEligibilityDecision(False, pid, cid, reason=f"prohibited:{reason}", mode=mode, layers=layers)

    # mode gating
    try:
        m = ExecutionMode(mode)
    except ValueError:
        return ProviderEligibilityDecision(False, pid, cid, reason="unknown_mode", mode=mode, layers=layers)
    if m in M32_PROHIBITED_MODES:
        return ProviderEligibilityDecision(False, pid, cid, reason=f"mode_prohibited:{m.value}", mode=mode, layers=layers)

    # side-effect ceiling
    try:
        sec = ProviderSideEffectClass(getattr(identity, "side_effect_class", ""))
    except ValueError:
        return ProviderEligibilityDecision(False, pid, cid, reason="unknown_side_effect", mode=mode, layers=layers)
    if sec not in (ProviderSideEffectClass.NONE, ProviderSideEffectClass.READ_ONLY):
        return ProviderEligibilityDecision(False, pid, cid, reason=f"side_effect_not_permitted:{sec.value}", mode=mode, layers=layers)

    # production certification (M25) remains required
    layers["production_certified"] = bool(production_certified)
    if not production_certified:
        return ProviderEligibilityDecision(False, pid, cid, reason="production_not_certified", mode=mode, layers=layers)

    # connector certification (M30) remains required
    layers["connector_certified"] = bool(connector_certified)
    if not connector_certified:
        return ProviderEligibilityDecision(False, pid, cid, reason="connector_not_certified", mode=mode, layers=layers)

    # provider configuration readiness (M32)
    if not config.enabled:
        layers["config_enabled"] = False
        return ProviderEligibilityDecision(False, pid, cid, reason="provider_config_disabled", mode=mode, layers=layers)
    try:
        validate_config(config)
        layers["config_valid"] = True
    except Exception as e:  # fail closed
        return ProviderEligibilityDecision(False, pid, cid, reason=f"config_invalid:{type(e).__name__}", mode=mode, layers=layers)

    # provider verification (M32) — READ-ONLY, never mutates the store
    vdec = resolve_provider_verification(
        pid, identity=identity, config=config, connector_manifest=connector_manifest,
        test_corpus_id=test_corpus_id, simulator_version=simulator_version, store=verification_store,
    )
    layers["provider_verification"] = {"allowed": vdec.allowed, "state": vdec.state, "reason": vdec.reason, "fresh": vdec.fresh}
    if not vdec.allowed:
        return ProviderEligibilityDecision(False, pid, cid, reason=f"verification:{vdec.reason}", mode=mode, layers=layers)

    # account + credential readiness (M31) — only relevant when the provider needs them
    needs_account = getattr(identity, "auth_profile", "none") not in ("none", "public", "sandbox_none")
    layers["needs_account"] = needs_account
    if needs_account:
        if not account_ready:
            return ProviderEligibilityDecision(False, pid, cid, reason="account_not_ready", mode=mode, layers=layers)
        if not credential_ready:
            return ProviderEligibilityDecision(False, pid, cid, reason="credential_not_ready", mode=mode, layers=layers)

    # approval remains required
    layers["approval_valid"] = bool(approval_valid)
    if not approval_valid:
        return ProviderEligibilityDecision(False, pid, cid, reason="approval_invalid", mode=mode, layers=layers)

    # rollout: production CANARY/ACTIVE require rollout AND are prohibited in M32.
    # SHADOW/SIMULATION/DRY_RUN are permitted with rollout OFF.
    layers["rollout_permits_production"] = bool(rollout_permits_production)

    return ProviderEligibilityDecision(True, pid, cid, reason="eligible_shadow_only", mode=mode, layers=layers)
