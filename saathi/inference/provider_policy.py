"""M21.0 — Canonical provider policy and per-provider kill switches.

Extends ``saathi.inference`` without creating a second ModelRouter or registry.
Provider *selection* remains ``ModelRouter``; this module states policy:

* which provider families exist
* production_supported vs pilot-only
* default enabled posture
* kill switches
* streaming / tool capability flags
* cost metadata placeholders (full cost ceilings → M21.2)

Kill switch env pattern (set to 1/true/on to disable):

    SAATHI_PROVIDER_KILL_<FAMILY>=1

Master hard kill (all inference providers via policy):

    SAATHI_INFERENCE_KILL_ALL=1
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderClass(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    FAKE = "fake"
    COMPAT = "compat"


class ProviderAvailability(str, Enum):
    """Static policy availability — not live health (live → M21.2)."""

    POLICY_ENABLED = "policy_enabled"
    POLICY_DISABLED = "policy_disabled"
    KILLED = "killed"
    MASTER_KILLED = "master_killed"
    UNSUPPORTED = "unsupported"


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CostMetadata:
    """Cost metadata placeholder — not a live billing authority (M21.2 expands)."""

    currency: str = "USD"
    cost_per_1k_input_usd: Optional[float] = None
    cost_per_1k_output_usd: Optional[float] = None
    relative_cost_per_1k: Optional[float] = None  # ModelRouter-scale
    known: bool = False
    notes: str = "placeholder; enforce ceilings in M21.2"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderPolicy:
    """Canonical policy row for one provider family."""

    family_id: str  # ollama, anthropic, openai, …
    provider_class: ProviderClass
    kill_switch_env: str
    production_supported: bool
    default_policy_enabled: bool  # when master inference on and not killed
    streaming: bool
    tool_calling: bool
    local: bool
    model_router_prefixes: tuple[str, ...] = ()
    llm_caller_key: str = ""  # saathi.llm DEFAULT_CALLERS key if any
    cost: CostMetadata = field(default_factory=CostMetadata)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provider_class"] = self.provider_class.value
        d["cost"] = self.cost.to_dict()
        d["model_router_prefixes"] = list(self.model_router_prefixes)
        return d


# Canonical policy table — single source for M21.0 kill-switch matrix.
PROVIDER_POLICIES: tuple[ProviderPolicy, ...] = (
    ProviderPolicy(
        family_id="ollama",
        provider_class=ProviderClass.LOCAL,
        kill_switch_env="SAATHI_PROVIDER_KILL_OLLAMA",
        production_supported=True,  # local-first pilot; live cert still env-blocked
        default_policy_enabled=True,
        streaming=True,
        tool_calling=False,
        local=True,
        model_router_prefixes=("ollama/",),
        llm_caller_key="ollama",
        cost=CostMetadata(
            relative_cost_per_1k=0.0,
            known=True,
            notes="local free relative cost; hardware constraints apply",
        ),
        notes="Canonical local engine for governed path",
    ),
    ProviderPolicy(
        family_id="fake",
        provider_class=ProviderClass.FAKE,
        kill_switch_env="SAATHI_PROVIDER_KILL_FAKE",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=True,
        cost=CostMetadata(relative_cost_per_1k=0.0, known=True, notes="test only"),
        notes="Deterministic tests only — never production",
    ),
    ProviderPolicy(
        family_id="openai_compat",
        provider_class=ProviderClass.COMPAT,
        kill_switch_env="SAATHI_PROVIDER_KILL_OPENAI_COMPAT",
        production_supported=False,
        default_policy_enabled=False,
        streaming=True,
        tool_calling=False,
        local=False,
        cost=CostMetadata(notes="compat endpoint; treat as cloud risk"),
        notes="Generic OpenAI-compatible HTTP; disabled in production policy",
    ),
    ProviderPolicy(
        family_id="anthropic",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_ANTHROPIC",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=True,
        local=False,
        model_router_prefixes=("anthropic/",),
        llm_caller_key="anthropic",
        cost=CostMetadata(relative_cost_per_1k=6.0, known=True),
        notes="Cloud; requires SAATHI_ALLOW_CLOUD_FALLBACK for governed cloud use",
    ),
    ProviderPolicy(
        family_id="openai",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_OPENAI",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=True,
        local=False,
        model_router_prefixes=("openai/",),
        llm_caller_key="openai",
        cost=CostMetadata(relative_cost_per_1k=5.0, known=True),
        notes="Cloud; default disabled under production policy",
    ),
    ProviderPolicy(
        family_id="groq",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_GROQ",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=False,
        model_router_prefixes=("groq/",),
        llm_caller_key="groq",
        cost=CostMetadata(relative_cost_per_1k=0.0, known=True, notes="often free tier"),
        notes="Cloud",
    ),
    ProviderPolicy(
        family_id="gemini",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_GEMINI",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=True,
        local=False,
        model_router_prefixes=("gemini/",),
        llm_caller_key="gemini",
        cost=CostMetadata(relative_cost_per_1k=0.0, known=True),
        notes="Cloud",
    ),
    ProviderPolicy(
        family_id="openrouter",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_OPENROUTER",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=False,
        model_router_prefixes=("deepseek/", "glm/", "qwen/"),
        llm_caller_key="",  # multi-family via openrouter
        cost=CostMetadata(notes="aggregates deepseek/glm/qwen"),
        notes="OpenRouter multiproxy; kill disables deepseek/glm/qwen policy family",
    ),
    ProviderPolicy(
        family_id="deepseek",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_DEEPSEEK",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=False,
        model_router_prefixes=("deepseek/",),
        llm_caller_key="deepseek",
        cost=CostMetadata(relative_cost_per_1k=0.3, known=True),
        notes="Cloud via OpenRouter-style caller",
    ),
    ProviderPolicy(
        family_id="glm",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_GLM",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=False,
        model_router_prefixes=("glm/",),
        llm_caller_key="glm",
        cost=CostMetadata(relative_cost_per_1k=0.5, known=True),
        notes="Cloud",
    ),
    ProviderPolicy(
        family_id="qwen",
        provider_class=ProviderClass.CLOUD,
        kill_switch_env="SAATHI_PROVIDER_KILL_QWEN",
        production_supported=False,
        default_policy_enabled=False,
        streaming=False,
        tool_calling=False,
        local=False,
        model_router_prefixes=("qwen/",),
        llm_caller_key="qwen",
        cost=CostMetadata(relative_cost_per_1k=0.4, known=True),
        notes="Cloud",
    ),
)

KILL_ALL_ENV = "SAATHI_INFERENCE_KILL_ALL"

_BY_ID: dict[str, ProviderPolicy] = {p.family_id: p for p in PROVIDER_POLICIES}


def get_provider_policy(family_id: str) -> Optional[ProviderPolicy]:
    return _BY_ID.get((family_id or "").strip().lower())


def kill_switch_env_keys() -> list[str]:
    keys = [KILL_ALL_ENV]
    keys.extend(p.kill_switch_env for p in PROVIDER_POLICIES)
    return keys


def is_master_killed() -> bool:
    return _env_bool(KILL_ALL_ENV, False)


def is_provider_killed(family_id: str) -> bool:
    if is_master_killed():
        return True
    pol = get_provider_policy(family_id)
    if pol is None:
        # Unknown family: fail closed for production policy consumers
        return True
    return _env_bool(pol.kill_switch_env, False)


def resolve_availability(
    family_id: str,
    *,
    master_inference_enabled: Optional[bool] = None,
    allow_cloud_fallback: Optional[bool] = None,
) -> ProviderAvailability:
    """Resolve static policy availability (not live health probes)."""
    if is_master_killed():
        return ProviderAvailability.MASTER_KILLED
    pol = get_provider_policy(family_id)
    if pol is None:
        return ProviderAvailability.UNSUPPORTED
    if _env_bool(pol.kill_switch_env, False):
        return ProviderAvailability.KILLED
    if not pol.production_supported and pol.provider_class is not ProviderClass.LOCAL:
        # cloud/compat/fake remain policy-disabled unless explicitly allowed later
        if pol.provider_class is ProviderClass.FAKE:
            return ProviderAvailability.UNSUPPORTED
    if master_inference_enabled is None:
        master_inference_enabled = _env_bool("SAATHI_INFERENCE_ENABLED", False)
    if allow_cloud_fallback is None:
        allow_cloud_fallback = _env_bool("SAATHI_ALLOW_CLOUD_FALLBACK", False)

    if pol.provider_class is ProviderClass.CLOUD:
        if not allow_cloud_fallback:
            return ProviderAvailability.POLICY_DISABLED
        if not pol.default_policy_enabled:
            return ProviderAvailability.POLICY_DISABLED
        if not master_inference_enabled:
            return ProviderAvailability.POLICY_DISABLED
        return ProviderAvailability.POLICY_ENABLED

    if pol.provider_class is ProviderClass.COMPAT:
        return ProviderAvailability.POLICY_DISABLED

    if pol.provider_class is ProviderClass.FAKE:
        return ProviderAvailability.UNSUPPORTED

    # LOCAL (ollama)
    if not pol.default_policy_enabled:
        return ProviderAvailability.POLICY_DISABLED
    if not master_inference_enabled:
        # Policy row allows local when masters on; masters off → policy_disabled
        return ProviderAvailability.POLICY_DISABLED
    return ProviderAvailability.POLICY_ENABLED


def is_provider_policy_enabled(family_id: str, **kwargs: Any) -> bool:
    return resolve_availability(family_id, **kwargs) is ProviderAvailability.POLICY_ENABLED


def family_for_model_router_name(provider_name: str) -> Optional[str]:
    """Map ModelRouter provider name (e.g. anthropic/claude) → family_id."""
    name = (provider_name or "").strip().lower()
    if not name:
        return None
    for pol in PROVIDER_POLICIES:
        for prefix in pol.model_router_prefixes:
            if name.startswith(prefix.lower()):
                return pol.family_id
    # bare family
    if name in _BY_ID:
        return name
    head = name.split("/", 1)[0]
    if head in _BY_ID:
        return head
    return None


def provider_policy_snapshot() -> dict[str, Any]:
    """Operator-safe snapshot (no secrets)."""
    rows = []
    for pol in PROVIDER_POLICIES:
        avail = resolve_availability(pol.family_id)
        rows.append(
            {
                **pol.to_dict(),
                "killed": is_provider_killed(pol.family_id),
                "kill_env_set": pol.kill_switch_env in os.environ,
                "availability": avail.value,
            }
        )
    return {
        "schema": "m21.0.provider_policy.v1",
        "milestone": "M21.0",
        "kill_all_env": KILL_ALL_ENV,
        "kill_all_active": is_master_killed(),
        "provider_count": len(rows),
        "providers": rows,
        "kill_switch_env_keys": kill_switch_env_keys(),
        "second_model_router": False,
        "notes": [
            "Kill switches disable policy use; they do not uninstall models",
            "Cloud remains behind SAATHI_ALLOW_CLOUD_FALLBACK (default off)",
            "Live health / cost ceilings formalized further in M21.2",
        ],
    }


def disable_provider_commands() -> dict[str, Any]:
    """Exact disable procedure for operators."""
    cmds = [f"export {KILL_ALL_ENV}=1  # hard-kill all providers via policy"]
    for pol in PROVIDER_POLICIES:
        cmds.append(f"export {pol.kill_switch_env}=1  # kill {pol.family_id}")
    cmds.append(
        "unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED "
        "SAATHI_ALLOW_CLOUD_FALLBACK  # master inference off"
    )
    return {
        "schema": "m21.0.provider_disable.v1",
        "commands": cmds,
        "revert_kill": f"unset {KILL_ALL_ENV} " + " ".join(p.kill_switch_env for p in PROVIDER_POLICIES),
    }
