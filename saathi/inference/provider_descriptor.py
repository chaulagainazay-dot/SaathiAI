"""M21.2 — Canonical provider descriptor derived from M21.0 provider policy.

Does not create a second registry: builds structured descriptors from
``PROVIDER_POLICIES`` plus versioned pricing / capability metadata.
Unknown values are never permissive defaults for paid cloud paths.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.inference.cost_policy import PricingMetadata, validate_pricing
from saathi.inference.provider_policy import (
    PROVIDER_POLICIES,
    ProviderClass,
    ProviderPolicy,
    get_provider_policy,
    is_master_killed,
    is_provider_killed,
    is_provider_policy_enabled,
)


DESCRIPTOR_VERSION = "m21.2.provider_descriptor.v1"

# Versioned pricing table (USD per million tokens). Not live-fetched.
# cost_updated_at is a fixed policy timestamp (not runtime now).
_PRICING_EPOCH = 1719792000.0  # 2024-07-01 UTC — policy version stamp

_PRIVACY_LOCAL = frozenset({"public", "internal", "confidential", "sensitive", "restricted"})
_PRIVACY_CLOUD = frozenset({"public", "internal"})  # restricted/sensitive never implicit cloud


def _env_present(*keys: str) -> Optional[bool]:
    """True if any key set non-empty; False if all absent; None if uncheckable."""
    seen = False
    for k in keys:
        if k in os.environ:
            seen = True
            if (os.environ.get(k) or "").strip():
                return True
    if seen:
        return False
    # Keys not observed — for local free providers treat as N/A; for cloud False
    return None


@dataclass(frozen=True)
class ProviderDescriptor:
    """Canonical provider descriptor for governance decisions."""

    provider_id: str
    provider_class: str
    display_name: str
    adapter_id: str
    environment: str  # any | test | production_pilot
    local_or_cloud: str
    enabled: bool
    configured: bool
    credential_required: bool
    credential_present: Optional[bool]
    certification_state: str  # production_supported | uncertified | test_only | fake
    production_supported: bool
    supported_capabilities: tuple[str, ...]
    supported_models: tuple[str, ...]
    model_classes: tuple[str, ...]
    streaming_supported: bool
    structured_output_supported: bool
    tool_use_supported: bool
    max_context_tokens: int
    max_output_tokens: int
    default_timeout_seconds: float
    max_timeout_seconds: float
    max_retries: int
    privacy_classes_allowed: tuple[str, ...]
    retention_constraints: str
    cloud_data_processing: bool
    pricing: PricingMetadata
    kill_switch_name: str
    circuit_breaker_key: str
    model_router_prefixes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["pricing"] = self.pricing.to_dict()
        d["supported_capabilities"] = list(self.supported_capabilities)
        d["supported_models"] = list(self.supported_models)
        d["model_classes"] = list(self.model_classes)
        d["privacy_classes_allowed"] = list(self.privacy_classes_allowed)
        d["model_router_prefixes"] = list(self.model_router_prefixes)
        return d


def _pricing_for(pol: ProviderPolicy) -> PricingMetadata:
    fid = pol.family_id
    if pol.provider_class is ProviderClass.LOCAL or pol.provider_class is ProviderClass.FAKE:
        return PricingMetadata(
            currency="USD",
            input_cost_per_million="0",
            output_cost_per_million="0",
            request_fixed_cost="0",
            cost_source="m21.2.provider_policy",
            cost_confidence="zero_marginal",
            cost_updated_at=_PRICING_EPOCH,
            zero_marginal=True,
            known=True,
            notes=pol.cost.notes or "local/fake zero marginal cost",
        )
    # Cloud: map relative costs into USD/M token placeholders when known
    # relative_cost_per_1k * 1000 ≈ relative per million scale (policy units)
    known = bool(pol.cost.known)
    rel = pol.cost.relative_cost_per_1k
    if known and rel is not None:
        # Convert ModelRouter-scale relative_cost_per_1k into rough USD/M:
        # 1.0 unit ≈ $1 / 1k tokens → $1000 / M (conservative placeholder)
        per_m = f"{float(rel) * 1000:.6f}"
        return PricingMetadata(
            currency=pol.cost.currency or "USD",
            input_cost_per_million=per_m,
            output_cost_per_million=per_m,
            request_fixed_cost="0",
            cost_source="m21.2.provider_policy.relative",
            cost_confidence="estimated" if not known else "known",
            cost_updated_at=_PRICING_EPOCH,
            zero_marginal=False,
            known=known,
            notes=pol.cost.notes or "",
        )
    return PricingMetadata(
        currency=pol.cost.currency or "USD",
        input_cost_per_million=None,
        output_cost_per_million=None,
        request_fixed_cost=None,
        cost_source="m21.2.provider_policy",
        cost_confidence="unknown",
        cost_updated_at=_PRICING_EPOCH,
        zero_marginal=False,
        known=False,
        notes=pol.cost.notes or "unknown price — ineligible for automatic paid fallback",
    )


def _credential_state(pol: ProviderPolicy) -> tuple[bool, Optional[bool]]:
    if pol.provider_class is ProviderClass.LOCAL:
        return False, None  # no API key; runtime health separate
    if pol.provider_class is ProviderClass.FAKE:
        return False, True
    # Cloud / compat
    key_map = {
        "anthropic": ("ANTHROPIC_API_KEY",),
        "openai": ("OPENAI_API_KEY",),
        "groq": ("GROQ_API_KEY",),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "openrouter": ("OPENROUTER_API_KEY",),
        "deepseek": ("DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"),
        "glm": ("GLM_API_KEY", "OPENROUTER_API_KEY"),
        "qwen": ("QWEN_API_KEY", "OPENROUTER_API_KEY"),
        "kimi": ("KIMI_API_KEY",),
        "nvidia_kimi": ("NVIDIA_API_KEY",),
        "openai_compat": ("OPENAI_API_KEY", "SAATHI_OPENAI_COMPAT_KEY"),
    }
    keys = key_map.get(pol.family_id, ())
    if not keys:
        return True, None  # required but unknown how to check
    present = _env_present(*keys)
    if present is None:
        return True, False  # cloud with no keys observed → absent
    return True, present


def _cert_state(pol: ProviderPolicy) -> str:
    if pol.provider_class is ProviderClass.FAKE:
        return "fake"
    if not pol.production_supported:
        if pol.provider_class is ProviderClass.LOCAL:
            return "production_pilot"  # local supported flag true for ollama
        return "uncertified"
    return "production_supported" if pol.production_supported else "uncertified"


def _configured(pol: ProviderPolicy, cred_req: bool, cred_present: Optional[bool]) -> bool:
    if pol.provider_class is ProviderClass.FAKE:
        return True
    if pol.provider_class is ProviderClass.LOCAL:
        # Local: configured if policy exists; runtime reachability separate
        return True
    if cred_req:
        return cred_present is True
    return True


def descriptor_from_policy(pol: ProviderPolicy) -> ProviderDescriptor:
    cred_req, cred_present = _credential_state(pol)
    configured = _configured(pol, cred_req, cred_present)
    local = pol.local or pol.provider_class is ProviderClass.LOCAL
    caps = ["screening", "standard", "fast", "private"]
    if pol.tool_calling:
        caps.append("tools")
    if pol.streaming:
        caps.append("streaming")
    privacy = tuple(sorted(_PRIVACY_LOCAL if local else _PRIVACY_CLOUD))
    cert = _cert_state(pol)
    if pol.provider_class is ProviderClass.FAKE:
        cert = "fake"
    elif not pol.production_supported:
        cert = "uncertified" if not local else "production_supported"
        if pol.family_id == "ollama":
            cert = "production_supported"  # local-first pilot; global production_certified still false

    adapter_map = {
        "ollama": "saathi.inference.adapters.ollama.OllamaEngine",
        "fake": "saathi.inference.adapters.fake.FakeEngine",
        "openai_compat": "saathi.inference.adapters.openai_compat.OpenAICompatEngine",
        "anthropic": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "openai": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "groq": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "gemini": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "openrouter": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "deepseek": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "glm": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "qwen": "saathi.inference.adapters.cloud.CloudCallerEngine",
        "kimi": "saathi.inference.adapters.kimi.KimiEngine",
        "nvidia_kimi": "saathi.inference.adapters.cloud.CloudCallerEngine",
    }

    return ProviderDescriptor(
        provider_id=pol.family_id,
        provider_class=pol.provider_class.value,
        display_name=pol.family_id.replace("_", " ").title(),
        adapter_id=adapter_map.get(pol.family_id, f"unknown:{pol.family_id}"),
        environment="test" if pol.provider_class is ProviderClass.FAKE else "any",
        local_or_cloud="local" if local else "cloud",
        enabled=is_provider_policy_enabled(pol.family_id),
        configured=configured,
        credential_required=cred_req,
        credential_present=cred_present,
        certification_state=cert,
        production_supported=bool(pol.production_supported),
        supported_capabilities=tuple(caps),
        supported_models=(
            ("kimi-k2.7-code", "kimi-k3")
            if pol.family_id == "kimi"
            else ("moonshotai/kimi-k3",)
            if pol.family_id == "nvidia_kimi"
            else tuple(pol.model_router_prefixes) or (pol.family_id,)
        ),
        model_classes=(
            ("coding_primary", "multimodal", "critical_expensive")
            if pol.family_id in {"kimi", "nvidia_kimi"}
            else ("local_small", "local_medium") if local else ("cloud_general",)
        ),
        streaming_supported=bool(pol.streaming),
        structured_output_supported=pol.family_id in {"kimi", "nvidia_kimi"},
        tool_use_supported=bool(pol.tool_calling),
        max_context_tokens=1_048_576 if pol.family_id in {"kimi", "nvidia_kimi"} else 8192 if local else 128000,
        max_output_tokens=4096 if local else 8192,
        default_timeout_seconds=60.0,
        max_timeout_seconds=600.0,
        max_retries=2 if pol.family_id in {"kimi", "nvidia_kimi"} else 0,
        privacy_classes_allowed=privacy,
        retention_constraints="metadata_only",
        cloud_data_processing=not local,
        pricing=_pricing_for(pol),
        kill_switch_name=pol.kill_switch_env,
        circuit_breaker_key=f"provider:{pol.family_id}",
        model_router_prefixes=tuple(pol.model_router_prefixes),
        metadata={
            "notes": pol.notes,
            "llm_caller_key": pol.llm_caller_key,
            "killed": is_provider_killed(pol.family_id),
            "master_killed": is_master_killed(),
        },
    )


def validate_descriptor(d: ProviderDescriptor) -> list[str]:
    errors: list[str] = []
    if not (d.provider_id or "").strip():
        errors.append("missing_provider_id")
    if d.provider_class not in {c.value for c in ProviderClass}:
        errors.append("unknown_provider_class")
    if d.max_context_tokens < 1:
        errors.append("invalid_max_context_tokens")
    if d.max_output_tokens < 1:
        errors.append("invalid_max_output_tokens")
    if d.default_timeout_seconds <= 0 or d.max_timeout_seconds <= 0:
        errors.append("invalid_timeout")
    if d.default_timeout_seconds > d.max_timeout_seconds:
        errors.append("default_timeout_exceeds_max")
    if d.max_retries < 0:
        errors.append("invalid_max_retries")
    if not d.supported_capabilities:
        errors.append("invalid_capability_declaration")
    errors.extend(validate_pricing(d.pricing))
    if d.local_or_cloud not in {"local", "cloud"}:
        errors.append("invalid_local_or_cloud")
    return errors


def list_descriptors() -> list[ProviderDescriptor]:
    return [descriptor_from_policy(p) for p in PROVIDER_POLICIES]


def get_descriptor(provider_id: str) -> Optional[ProviderDescriptor]:
    pol = get_provider_policy(provider_id)
    if pol is None:
        return None
    return descriptor_from_policy(pol)


def assert_unique_provider_ids() -> None:
    ids = [p.family_id for p in PROVIDER_POLICIES]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate provider IDs in PROVIDER_POLICIES")


def descriptor_snapshot() -> dict[str, Any]:
    assert_unique_provider_ids()
    rows = []
    for d in list_descriptors():
        rows.append(
            {
                **d.to_dict(),
                "validation_errors": validate_descriptor(d),
            }
        )
    return {
        "schema": DESCRIPTOR_VERSION,
        "milestone": "M21.2",
        "provider_count": len(rows),
        "providers": rows,
        "production_certified": False,
        "second_registry": False,
        "extends": "m21.0.provider_policy",
        "checked_at": time.time(),
    }
