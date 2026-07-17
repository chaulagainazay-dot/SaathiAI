"""M21.0 — Residual inference / LLM call-path inventory.

Machine-readable map of known paths. Does **not** migrate callers (M21.1).
Does **not** replace ModelRouter or ExecutionGateway.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class PathClass(str, Enum):
    """Authority classification for an inference/LLM entrypoint."""

    CANONICAL_GOVERNED = "canonical_governed"  # ExecutionGateway / governed local path
    CANONICAL_SELECTION = "canonical_selection"  # ModelRouter only
    CANONICAL_LEGACY = "canonical_legacy"  # saathi.llm.generate (still default for many)
    OPT_IN_ADOPTED = "opt_in_adopted"  # M20.3 dual-mode callers
    ENGINE_ADAPTER = "engine_adapter"  # inference engine implementations
    RESIDUAL_DIRECT = "residual_direct"  # known remaining direct/legacy surfaces
    AGGREGATOR = "aggregator"  # read-only status / console
    OUT_OF_SCOPE = "out_of_scope"  # non-LLM "generate" names


class MigrationStatus(str, Enum):
    AUTHORITATIVE = "authoritative"
    DEFAULT_LEGACY = "default_legacy"
    OPT_IN = "opt_in"
    INVENTORIED = "inventoried"  # known; not migrated this slice
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class CallPath:
    path_id: str
    module: str
    entry: str
    classification: PathClass
    migration: MigrationStatus
    default_enabled: bool
    uses_model_router: bool
    uses_governed_gateway: bool
    can_reach_cloud: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["classification"] = self.classification.value
        d["migration"] = self.migration.value
        return d


# Static inventory — update when new residual paths are discovered (M21.1+).
CALL_PATH_INVENTORY: tuple[CallPath, ...] = (
    CallPath(
        path_id="model_router",
        module="saathi.model_router",
        entry="ModelRouter.route",
        classification=PathClass.CANONICAL_SELECTION,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=True,
        uses_model_router=True,
        uses_governed_gateway=False,
        can_reach_cloud=False,  # selection only
        notes="Sole model-selection authority; no network I/O",
    ),
    CallPath(
        path_id="governed_local_gateway",
        module="saathi.inference.gateway_path",
        entry="execute_governed_local_inference",
        classification=PathClass.CANONICAL_GOVERNED,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=False,
        uses_model_router=True,
        uses_governed_gateway=True,
        can_reach_cloud=False,
        notes="M20.2 path; dual flags SAATHI_INFERENCE_* default off",
    ),
    CallPath(
        path_id="model_gateway_orchestrator",
        module="saathi.execution.orchestrators.model_gateway",
        entry="ModelGateway",
        classification=PathClass.CANONICAL_GOVERNED,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=False,
        uses_model_router=True,
        uses_governed_gateway=True,
        can_reach_cloud=False,
        notes="ExecutionGateway model orchestrator; routes to governed path when enabled",
    ),
    CallPath(
        path_id="legacy_llm_generate",
        module="saathi.llm",
        entry="generate",
        classification=PathClass.CANONICAL_LEGACY,
        migration=MigrationStatus.DEFAULT_LEGACY,
        default_enabled=True,
        uses_model_router=True,
        uses_governed_gateway=False,
        can_reach_cloud=True,
        notes="Default chat/tool path for most callers; M21.1 targets residual direct use",
    ),
    CallPath(
        path_id="cheap_ask",
        module="saathi.tools.cheap_llm",
        entry="cheap_ask",
        classification=PathClass.OPT_IN_ADOPTED,
        migration=MigrationStatus.OPT_IN,
        default_enabled=True,  # tool exists; rollout mode legacy by default
        uses_model_router=True,
        uses_governed_gateway=False,  # only when rollout not legacy
        can_reach_cloud=True,
        notes="M20.3 opt-in; SAATHI_INF_ROLLOUT_CHEAP_ASK default legacy",
    ),
    CallPath(
        path_id="prose_clean",
        module="saathi.tools.prose",
        entry="prose_clean",
        classification=PathClass.OPT_IN_ADOPTED,
        migration=MigrationStatus.OPT_IN,
        default_enabled=True,
        uses_model_router=True,
        uses_governed_gateway=False,
        can_reach_cloud=True,
        notes="M20.3 opt-in; SAATHI_INF_ROLLOUT_PROSE_CLEAN default legacy",
    ),
    CallPath(
        path_id="compat_adopt_generate",
        module="saathi.inference.compat",
        entry="adopt_generate",
        classification=PathClass.OPT_IN_ADOPTED,
        migration=MigrationStatus.OPT_IN,
        default_enabled=False,
        uses_model_router=True,
        uses_governed_gateway=True,
        can_reach_cloud=True,
        notes="Rollout adapter over governed path + legacy fallback",
    ),
    CallPath(
        path_id="engine_ollama",
        module="saathi.inference.adapters.ollama",
        entry="OllamaEngine",
        classification=PathClass.ENGINE_ADAPTER,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=False,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=False,
        notes="Local engine adapter; reached only via registry/runtime/gateway",
    ),
    CallPath(
        path_id="engine_cloud_caller",
        module="saathi.inference.adapters.cloud",
        entry="CloudCallerEngine",
        classification=PathClass.ENGINE_ADAPTER,
        migration=MigrationStatus.INVENTORIED,
        default_enabled=False,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=True,
        notes="Cloud engine wrapper; must stay behind allow_cloud_fallback + kill switches",
    ),
    CallPath(
        path_id="engine_openai_compat",
        module="saathi.inference.adapters.openai_compat",
        entry="OpenAICompatEngine",
        classification=PathClass.ENGINE_ADAPTER,
        migration=MigrationStatus.INVENTORIED,
        default_enabled=False,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=True,
        notes="OpenAI-compatible HTTP engine; production_supported=false by default policy",
    ),
    CallPath(
        path_id="engine_fake",
        module="saathi.inference.adapters.fake",
        entry="FakeEngine",
        classification=PathClass.ENGINE_ADAPTER,
        migration=MigrationStatus.NOT_APPLICABLE,
        default_enabled=False,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=False,
        notes="Test/deterministic only",
    ),
    CallPath(
        path_id="runtime_generate_with_fallback",
        module="saathi.inference.runtime",
        entry="generate_with_fallback",
        classification=PathClass.CANONICAL_GOVERNED,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=False,
        uses_model_router=True,
        uses_governed_gateway=False,
        can_reach_cloud=True,
        notes="M20.1 runtime helper; respects InferenceSettings cloud policy",
    ),
    CallPath(
        path_id="chat_engine",
        module="saathi.chat.engine",
        entry="ChatLLMAdapter",
        classification=PathClass.CANONICAL_GOVERNED,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=True,
        uses_model_router=True,
        uses_governed_gateway=True,
        can_reach_cloud=True,
        notes="M23: governed chat runtime default; chat_adapter → chat.runtime → ModelRouter/adapters",
    ),
    CallPath(
        path_id="chat_runtime",
        module="saathi.chat.runtime",
        entry="run_chat_completion",
        classification=PathClass.CANONICAL_GOVERNED,
        migration=MigrationStatus.AUTHORITATIVE,
        default_enabled=True,
        uses_model_router=True,
        uses_governed_gateway=True,
        can_reach_cloud=True,
        notes="M23 sole production chat execution authority",
    ),
    CallPath(
        path_id="openjarvis_execution_adapter",
        module="saathi.execution.adapters.openjarvis_adapter",
        entry="OpenJarvisAdapter",
        classification=PathClass.RESIDUAL_DIRECT,
        migration=MigrationStatus.INVENTORIED,
        default_enabled=False,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=False,
        notes="Offline SUCCESS stub when inference disabled; no OJ process",
    ),
    CallPath(
        path_id="m20_console_inference",
        module="saathi.m20_console.status",
        entry="inference_snapshot",
        classification=PathClass.AGGREGATOR,
        migration=MigrationStatus.NOT_APPLICABLE,
        default_enabled=True,
        uses_model_router=False,
        uses_governed_gateway=False,
        can_reach_cloud=False,
        notes="Read-only; never generates",
    ),
)


def path_inventory_snapshot() -> dict[str, Any]:
    """Privacy-safe inventory for operators and tests."""
    rows = [p.to_dict() for p in CALL_PATH_INVENTORY]
    by_class: dict[str, int] = {}
    residual = []
    cloud_capable = []
    for p in CALL_PATH_INVENTORY:
        by_class[p.classification.value] = by_class.get(p.classification.value, 0) + 1
        if p.classification is PathClass.RESIDUAL_DIRECT:
            residual.append(p.path_id)
        if p.can_reach_cloud:
            cloud_capable.append(p.path_id)
    return {
        "schema": "m21.0.path_inventory.v1",
        "milestone": "M21.0",
        "path_count": len(rows),
        "by_classification": by_class,
        "residual_direct_ids": residual,
        "cloud_capable_path_ids": cloud_capable,
        "second_model_router": False,
        "second_inference_package": False,
        "paths": rows,
        "m21_1_deferred": [
            "migrate residual chat default",
            "block new direct caller→provider registrations",
            "enforce contract on all non-legacy paths",
        ],
    }


def residual_direct_paths() -> list[CallPath]:
    return [p for p in CALL_PATH_INVENTORY if p.classification is PathClass.RESIDUAL_DIRECT]


def get_path(path_id: str) -> CallPath | None:
    for p in CALL_PATH_INVENTORY:
        if p.path_id == path_id:
            return p
    return None
