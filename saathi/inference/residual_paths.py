"""M21.1 — Residual inference path controls and allowlist.

Every non-canonical path must be classified. New copies of legacy patterns
are blocked by the static bypass guard (see bypass_guard.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ResidualDisposition(str, Enum):
    CANONICAL = "canonical"
    MIGRATE_NOW = "migrate_now"
    COMPATIBILITY_ADAPTER = "compatibility_adapter"
    LEGACY_ALLOWED_TEMPORARILY = "legacy_allowed_temporarily"
    TEST_ONLY = "test_only"
    FAKE_PROVIDER = "fake_provider"
    DIRECT_PROVIDER_BYPASS = "direct_provider_bypass"
    BLOCK = "block"
    DEFER_WITH_GUARD = "defer_with_guard"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResidualPathControl:
    path_id: str
    module: str
    symbol: str
    disposition: ResidualDisposition
    reason: str
    expiry_milestone: str
    allowed_behavior: str
    telemetry_tag: str
    new_callers_forbidden: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["disposition"] = self.disposition.value
        return d


RESIDUAL_PATH_CONTROLS: tuple[ResidualPathControl, ...] = (
    ResidualPathControl(
        path_id="model_router",
        module="saathi.model_router",
        symbol="ModelRouter",
        disposition=ResidualDisposition.CANONICAL,
        reason="Sole model-selection authority",
        expiry_milestone="n/a",
        allowed_behavior="selection only",
        telemetry_tag="canonical_selection",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="governed_local_gateway",
        module="saathi.inference.gateway_path",
        symbol="execute_governed_local_inference",
        disposition=ResidualDisposition.CANONICAL,
        reason="M20.2/M21 governed execution",
        expiry_milestone="n/a",
        allowed_behavior="contract-validated local inference",
        telemetry_tag="canonical_governed",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="model_gateway_orchestrator",
        module="saathi.execution.orchestrators.model_gateway",
        symbol="ModelGateway",
        disposition=ResidualDisposition.CANONICAL,
        reason="ExecutionGateway model path",
        expiry_milestone="n/a",
        allowed_behavior="ToolIntent → governed or OJ stub",
        telemetry_tag="canonical_gateway",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="legacy_llm_generate",
        module="saathi.llm",
        symbol="generate",
        disposition=ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY,
        reason="Default multi-provider execution for unmigrated callers",
        expiry_milestone="M21.3",
        allowed_behavior="ModelRouter chain + DEFAULT_CALLERS; no new direct SDKs",
        telemetry_tag="legacy_llm",
    ),
    ResidualPathControl(
        path_id="cheap_ask",
        module="saathi.tools.cheap_llm",
        symbol="cheap_ask",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3 adopted; M21.2 routes via provider decision + compat/legacy",
        expiry_milestone="M21.3",
        allowed_behavior="compat + legacy generate; no direct proxy",
        telemetry_tag="compat_cheap_ask",
    ),
    ResidualPathControl(
        path_id="prose_clean",
        module="saathi.tools.prose",
        symbol="clean_prose",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3 adopted",
        expiry_milestone="M21.3",
        allowed_behavior="compat adapter + legacy generate",
        telemetry_tag="compat_prose",
    ),
    ResidualPathControl(
        path_id="compat_adopt_generate",
        module="saathi.inference.compat",
        symbol="adopt_generate",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3/M21.1 compatibility layer",
        expiry_milestone="n/a",
        allowed_behavior="build canonical request + rollout",
        telemetry_tag="compat_core",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="engine_ollama",
        module="saathi.inference.adapters.ollama",
        symbol="OllamaEngine",
        disposition=ResidualDisposition.CANONICAL,
        reason="Local engine adapter only",
        expiry_milestone="n/a",
        allowed_behavior="adapter under registry/gateway",
        telemetry_tag="engine_ollama",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="engine_cloud_caller",
        module="saathi.inference.adapters.cloud",
        symbol="CloudCallerEngine",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Cloud wrapper; production_supported=false; M21.2 cost/availability governed",
        expiry_milestone="M21.3",
        allowed_behavior="behind allow_cloud_fallback + provider decision only",
        telemetry_tag="engine_cloud",
    ),
    ResidualPathControl(
        path_id="engine_openai_compat",
        module="saathi.inference.adapters.openai_compat",
        symbol="OpenAICompatEngine",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Generic HTTP; policy-disabled by default",
        expiry_milestone="M21.3",
        allowed_behavior="policy-disabled unless explicitly enabled via decision layer",
        telemetry_tag="engine_compat",
    ),
    ResidualPathControl(
        path_id="engine_fake",
        module="saathi.inference.adapters.fake",
        symbol="FakeEngine",
        disposition=ResidualDisposition.FAKE_PROVIDER,
        reason="Tests only",
        expiry_milestone="n/a",
        allowed_behavior="deterministic tests",
        telemetry_tag="engine_fake",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="runtime_generate_with_fallback",
        module="saathi.inference.runtime",
        symbol="generate_with_fallback",
        disposition=ResidualDisposition.CANONICAL,
        reason="M20.1 runtime helper",
        expiry_milestone="n/a",
        allowed_behavior="settings-gated multi-engine",
        telemetry_tag="runtime_fallback",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="chat_engine",
        module="saathi.chat.engine",
        symbol="ChatLLMAdapter / _default_llm",
        disposition=ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY,
        reason="Chat default remains legacy; full migration out of M21.1 scope",
        expiry_milestone="M23",
        allowed_behavior="llm.generate via ModelRouter; no silent unauthorized cloud kill bypass",
        telemetry_tag="legacy_chat",
    ),
    ResidualPathControl(
        path_id="openjarvis_execution_adapter",
        module="saathi.execution.adapters.openjarvis_adapter",
        symbol="OpenJarvisAdapter",
        disposition=ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY,
        reason="Offline SUCCESS stub when inference disabled",
        expiry_milestone="M21.3",
        allowed_behavior="no OJ process; stub only",
        telemetry_tag="oj_stub",
    ),
    ResidualPathControl(
        path_id="m20_console_inference",
        module="saathi.m20_console.status",
        symbol="inference_snapshot",
        disposition=ResidualDisposition.CANONICAL,
        reason="Read-only aggregator",
        expiry_milestone="n/a",
        allowed_behavior="no generation",
        telemetry_tag="console",
        new_callers_forbidden=False,
    ),
    # Additional residual found beyond M21.0 inventory
    ResidualPathControl(
        path_id="cheap_ask_legacy_proxy",
        module="saathi.tools.cheap_llm",
        symbol="httpx.post CHEAP_PROXY_URL (removed)",
        disposition=ResidualDisposition.BLOCK,
        reason="M21.2 removed direct anthropic-proxy invoke from cheap_ask",
        expiry_milestone="n/a",
        allowed_behavior="blocked; cheap_proxy_status remains read-only health check only",
        telemetry_tag="legacy_proxy_blocked",
    ),
    ResidualPathControl(
        path_id="provider_governance",
        module="saathi.inference.provider_governance",
        symbol="decide_providers / CLI",
        disposition=ResidualDisposition.CANONICAL,
        reason="M21.2 canonical provider decision layer",
        expiry_milestone="n/a",
        allowed_behavior="availability, cost, failover, circuit governance",
        telemetry_tag="provider_governance",
        new_callers_forbidden=False,
    ),
    ResidualPathControl(
        path_id="tools_llm_helper",
        module="saathi.tools._llm_helper",
        symbol="ask_llm",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Hardcoded provider chain pre-router era residual",
        expiry_milestone="M21.3",
        allowed_behavior="existing tools only; static guard blocks new api.openai copies outside allowlist",
        telemetry_tag="tools_llm_helper",
    ),
    ResidualPathControl(
        path_id="agent_sdk_clients",
        module="saathi.agent",
        symbol="OpenAI/Anthropic client construction",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Legacy agent multi-provider clients; out of M21.1 migration scope",
        expiry_milestone="M22",
        allowed_behavior="existing agent.py only",
        telemetry_tag="legacy_agent",
    ),
    ResidualPathControl(
        path_id="server_direct_http",
        module="saathi.server",
        symbol="direct provider HTTP (e.g. groq)",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Legacy server surfaces; static guard allowlisted only this file",
        expiry_milestone="M21.3",
        allowed_behavior="existing server.py only; no new provider URL copies",
        telemetry_tag="legacy_server",
    ),
    ResidualPathControl(
        path_id="tools_research",
        module="saathi.tools.research",
        symbol="generativelanguage URL",
        disposition=ResidualDisposition.DEFER_WITH_GUARD,
        reason="Research tool residual",
        expiry_milestone="M21.3",
        allowed_behavior="existing research.py only",
        telemetry_tag="tools_research",
    ),
)


_BY_ID = {p.path_id: p for p in RESIDUAL_PATH_CONTROLS}


def get_residual_control(path_id: str) -> ResidualPathControl | None:
    return _BY_ID.get(path_id)


def residual_paths_snapshot() -> dict[str, Any]:
    by_disp: dict[str, list[str]] = {}
    for p in RESIDUAL_PATH_CONTROLS:
        by_disp.setdefault(p.disposition.value, []).append(p.path_id)
    return {
        "schema": "m21.1.residual_paths.v1",
        "milestone": "M21.1",
        "path_count": len(RESIDUAL_PATH_CONTROLS),
        "by_disposition": by_disp,
        "paths": [p.to_dict() for p in RESIDUAL_PATH_CONTROLS],
        "unclassified_forbidden": True,
        "new_legacy_copies_forbidden": True,
    }


def legacy_allowed_path_ids() -> list[str]:
    return [
        p.path_id
        for p in RESIDUAL_PATH_CONTROLS
        if p.disposition is ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY
    ]
