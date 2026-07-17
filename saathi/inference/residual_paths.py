"""M21.3 — Residual inference path controls and classification.

Every non-canonical path must be classified. New copies of legacy patterns
are blocked by the static bypass guard and release_check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ResidualDisposition(str, Enum):
    CANONICAL = "canonical"
    MIGRATE_NOW = "migrate_now"
    COMPATIBILITY_ADAPTER = "compatibility_adapter"
    COMPATIBILITY_WRAPPED = "compatibility_wrapped"
    LEGACY_ALLOWED_TEMPORARILY = "legacy_allowed_temporarily"
    EXPLICIT_LEGACY_EXCEPTION = "explicit_legacy_exception"
    TEST_ONLY = "test_only"
    FAKE_PROVIDER = "fake_provider"
    DIRECT_PROVIDER_BYPASS = "direct_provider_bypass"
    BLOCK = "block"
    BLOCKED = "blocked"
    DEFER_WITH_GUARD = "defer_with_guard"
    DEAD_CODE_REMOVE = "dead_code_remove"
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
    caller_id: str = ""
    production_reachability: bool = False

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
        production_reachability=True,
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
        caller_id="execution_gateway",
        production_reachability=True,
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
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="legacy_llm_generate",
        module="saathi.llm",
        symbol="generate",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M22 pure compatibility facade; HTTP in adapters.http_providers",
        expiry_milestone="n/a",
        allowed_behavior="preflight + ModelRouter + invoke_family transport; frozen call sites",
        telemetry_tag="compat_llm",
        caller_id="legacy_llm_generate",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="http_providers_transport",
        module="saathi.inference.adapters.http_providers",
        symbol="DEFAULT_FAMILY_CALLERS / invoke_family",
        disposition=ResidualDisposition.CANONICAL,
        reason="M22 canonical multi-family HTTP transport",
        expiry_milestone="n/a",
        allowed_behavior="adapter package only; credentials + URLs confined here",
        telemetry_tag="http_providers",
        new_callers_forbidden=False,
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="cheap_ask",
        module="saathi.tools.cheap_llm",
        symbol="cheap_ask",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3 adopted; M21.2/M21.3 routes via provider decision + compat",
        expiry_milestone="M22",
        allowed_behavior="compat + legacy generate; no direct proxy",
        telemetry_tag="compat_cheap_ask",
        caller_id="cheap_ask",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="prose_clean",
        module="saathi.tools.prose",
        symbol="clean_prose",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3 adopted",
        expiry_milestone="M22",
        allowed_behavior="compat adapter + legacy generate",
        telemetry_tag="compat_prose",
        caller_id="prose_clean",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="compat_adopt_generate",
        module="saathi.inference.compat",
        symbol="adopt_generate",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M20.3/M21 compatibility layer",
        expiry_milestone="n/a",
        allowed_behavior="build canonical request + rollout",
        telemetry_tag="compat_core",
        new_callers_forbidden=False,
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="chat_adapter",
        module="saathi.inference.chat_adapter",
        symbol="chat_generate",
        disposition=ResidualDisposition.COMPATIBILITY_ADAPTER,
        reason="M23 thin facade; delegates only to saathi.chat.runtime",
        expiry_milestone="n/a",
        allowed_behavior="normalize + run_chat_completion; no provider execution",
        telemetry_tag="chat_adapter",
        new_callers_forbidden=False,
        caller_id="chat_engine",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="chat_runtime",
        module="saathi.chat.runtime",
        symbol="run_chat_completion",
        disposition=ResidualDisposition.CANONICAL,
        reason="M23 sole production chat execution authority",
        expiry_milestone="n/a",
        allowed_behavior="ChatRequest → preflight → InferenceRequest → ModelRouter/adapters",
        telemetry_tag="chat_runtime",
        new_callers_forbidden=False,
        caller_id="chat_engine",
        production_reachability=True,
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
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="engine_cloud_caller",
        module="saathi.inference.adapters.cloud",
        symbol="CloudCallerEngine",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="Cloud wrapper; production_supported=false; M21.2 governed",
        expiry_milestone="M24",
        allowed_behavior="behind allow_cloud_fallback + provider decision only",
        telemetry_tag="engine_cloud",
        production_reachability=False,
    ),
    ResidualPathControl(
        path_id="engine_openai_compat",
        module="saathi.inference.adapters.openai_compat",
        symbol="OpenAICompatEngine",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="Generic HTTP; policy-disabled by default",
        expiry_milestone="M24",
        allowed_behavior="policy-disabled unless explicitly enabled via decision layer",
        telemetry_tag="engine_compat",
        production_reachability=False,
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
        caller_id="fake_engine",
        production_reachability=False,
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
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="chat_engine",
        module="saathi.chat.engine",
        symbol="ChatLLMAdapter / _default_llm",
        disposition=ResidualDisposition.CANONICAL,
        reason="M23 routes through chat_adapter → chat.runtime; public API preserved",
        expiry_milestone="n/a",
        allowed_behavior="chat_adapter only; no direct provider in chat package",
        telemetry_tag="chat_canonical",
        caller_id="chat_engine",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="openjarvis_execution_adapter",
        module="saathi.execution.adapters.openjarvis_adapter",
        symbol="OpenJarvisAdapter",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="M22: offline SUCCESS stub or OllamaEngine when inference enabled; no OJ process",
        expiry_milestone="n/a",
        allowed_behavior="stub only when disabled; OllamaEngine when enabled; no direct provider SDK",
        telemetry_tag="oj_stub",
        production_reachability=False,
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
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="cheap_ask_legacy_proxy",
        module="saathi.tools.cheap_llm",
        symbol="httpx.post CHEAP_PROXY_URL (removed)",
        disposition=ResidualDisposition.BLOCK,
        reason="M21.2 removed direct anthropic-proxy invoke from cheap_ask",
        expiry_milestone="n/a",
        allowed_behavior="blocked; cheap_proxy_status remains read-only health check only",
        telemetry_tag="legacy_proxy_blocked",
        production_reachability=False,
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
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="tools_llm_helper",
        module="saathi.tools._llm_helper",
        symbol="ask_llm",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="M21.3 removed direct HTTP chain; delegates to llm.generate",
        expiry_milestone="M22",
        allowed_behavior="preflight + generate only",
        telemetry_tag="tools_llm_helper",
        caller_id="tools_llm_helper",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="agent_runtime_governed",
        module="saathi.agent",
        symbol="SaathiAgent complete/respond",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="M22 agent orchestration; SDK clients in adapters.agent_provider",
        expiry_milestone="n/a",
        allowed_behavior="preflight + agent_provider session; no SDK in agent.py",
        telemetry_tag="agent_governed",
        caller_id="agent_runtime",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="agent_provider_adapter",
        module="saathi.inference.adapters.agent_provider",
        symbol="build_agent_session / AgentProviderSession",
        disposition=ResidualDisposition.CANONICAL,
        reason="M22 canonical agent provider transport",
        expiry_milestone="n/a",
        allowed_behavior="adapter package only; owns OpenAI/Anthropic clients",
        telemetry_tag="agent_provider",
        new_callers_forbidden=False,
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="server_direct_http",
        module="saathi.server",
        symbol="groq health probe / ask_llm routes",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="Server uses ask_llm (tools helper); health probe is non-generate",
        expiry_milestone="M22",
        allowed_behavior="no new provider URL copies; inference via tools_llm_helper",
        telemetry_tag="legacy_server",
        caller_id="server_tools",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="tools_research",
        module="saathi.tools.research",
        symbol="_grounded / research",
        disposition=ResidualDisposition.COMPATIBILITY_WRAPPED,
        reason="M22 research facade; grounding via adapters.grounding",
        expiry_milestone="n/a",
        allowed_behavior="preflight + grounded_generate; no direct Gemini URL",
        telemetry_tag="tools_research",
        caller_id="research_tools",
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="research_grounding_adapter",
        module="saathi.inference.adapters.grounding",
        symbol="grounded_generate",
        disposition=ResidualDisposition.CANONICAL,
        reason="M22 canonical google_search grounding transport",
        expiry_milestone="n/a",
        allowed_behavior="capability-specific adapter; no silent non-grounded fallback",
        telemetry_tag="research_grounding",
        new_callers_forbidden=False,
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="legacy_facade_preflight",
        module="saathi.inference.legacy_facade",
        symbol="preflight_inference",
        disposition=ResidualDisposition.CANONICAL,
        reason="Shared residual preflight gate",
        expiry_milestone="n/a",
        allowed_behavior="kill + caller policy; no provider execution",
        telemetry_tag="legacy_preflight",
        new_callers_forbidden=False,
        production_reachability=True,
    ),
    ResidualPathControl(
        path_id="release_check",
        module="saathi.inference.release_check",
        symbol="run_release_check",
        disposition=ResidualDisposition.CANONICAL,
        reason="M21.3 release architecture enforcement",
        expiry_milestone="n/a",
        allowed_behavior="static offline checks",
        telemetry_tag="release_check",
        new_callers_forbidden=False,
        production_reachability=False,
    ),
    ResidualPathControl(
        path_id="transitional_unknown_caller",
        module="saathi.inference.caller_policy",
        symbol="unknown",
        disposition=ResidualDisposition.BLOCK,
        reason="M21.3 disabled FORBIDDEN; production acceptance removed",
        expiry_milestone="n/a",
        allowed_behavior="denied in all environments",
        telemetry_tag="unknown_blocked",
        caller_id="unknown",
        production_reachability=False,
    ),
)


_BY_ID = {p.path_id: p for p in RESIDUAL_PATH_CONTROLS}


def get_residual_control(path_id: str) -> ResidualPathControl | None:
    return _BY_ID.get(path_id)


def residual_paths_snapshot() -> dict[str, Any]:
    by_disp: dict[str, list[str]] = {}
    for p in RESIDUAL_PATH_CONTROLS:
        by_disp.setdefault(p.disposition.value, []).append(p.path_id)
    unknown = by_disp.get(ResidualDisposition.UNKNOWN.value, [])
    bypass = by_disp.get(ResidualDisposition.DIRECT_PROVIDER_BYPASS.value, [])
    return {
        "schema": "m23.residual_paths.v1",
        "milestone": "M23",
        "path_count": len(RESIDUAL_PATH_CONTROLS),
        "by_disposition": by_disp,
        "paths": [p.to_dict() for p in RESIDUAL_PATH_CONTROLS],
        "unknown_count": len(unknown),
        "direct_provider_bypass_count": len(bypass),
        "explicit_legacy_exception_count": len(
            by_disp.get(ResidualDisposition.EXPLICIT_LEGACY_EXCEPTION.value, [])
        ),
        "chat_residual_exception_count": 0,
        "unclassified_forbidden": True,
        "new_legacy_copies_forbidden": True,
        "production_certified": False,
    }


def legacy_allowed_path_ids() -> list[str]:
    return [
        p.path_id
        for p in RESIDUAL_PATH_CONTROLS
        if p.disposition
        in {
            ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY,
            ResidualDisposition.EXPLICIT_LEGACY_EXCEPTION,
        }
    ]


def main() -> int:
    import json
    import sys

    print(json.dumps(residual_paths_snapshot(), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
