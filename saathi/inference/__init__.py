"""SaathiOS unified inference runtime (M20.1) + governed gateway path (M20.2)
+ opt-in caller adoption (M20.3).

OpenJarvis-informed, SaathiOS-native. This package provides:

* ``InferenceEngine`` contract (generate/stream/health/list_models/…)
* engine registration and optional discovery
* model catalogue with capability provenance
* local hardware capability profile (M2 8 GB aware)
* bounded benchmark harness
* observation feed into the existing ``ModelRouter`` (which remains authoritative)
* M20.2 governed ExecutionGateway local inference path (default-off)
* M20.3 opt-in migration for ≤2 low-risk callers (default legacy)

Disabled by default. Does **not** replace ModelRouter, ExecutionGateway,
mission engine, memory governance, or Trading Guardian. Does **not** run
OpenJarvis as a process. Does **not** switch global chat.
"""
from __future__ import annotations

from saathi.inference.catalogue import (
    CapabilityProvenance,
    ModelCatalogue,
    ModelRecord,
    get_default_catalogue,
)
from saathi.inference.caller_rollout import InfRolloutMode, resolve_mode, rollout_snapshot
from saathi.inference.compat import (
    adopt_generate,
    cheap_ask_adopted,
    metrics_snapshot as compat_metrics_snapshot,
    prose_clean_adopted,
)
from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.engine import (
    EngineCapabilities,
    GenerateResult,
    InferenceEngine,
    StreamChunk,
)
from saathi.inference.errors import (
    EngineError,
    EngineTimeoutError,
    EngineUnhealthyError,
    InferenceError,
    NormalizedError,
    normalize_error,
)
from saathi.inference.hardware import HardwareProfile, profile_local_hardware
from saathi.inference.registry import EngineRegistry, get_engine_registry
from saathi.inference.gateway_path import (
    GovernedLocalInferencePath,
    execute_governed_local_inference,
)
from saathi.inference.live_validation import LiveValidationReport, run_live_small_model_validation
from saathi.inference.request import InferenceRequest, Sensitivity
from saathi.inference.result import StructuredInferenceResult

__all__ = [
    "CapabilityProvenance",
    "EngineCapabilities",
    "EngineError",
    "EngineRegistry",
    "EngineTimeoutError",
    "EngineUnhealthyError",
    "GenerateResult",
    "GovernedLocalInferencePath",
    "HardwareProfile",
    "InfRolloutMode",
    "InferenceEngine",
    "InferenceError",
    "InferenceRequest",
    "InferenceSettings",
    "LiveValidationReport",
    "ModelCatalogue",
    "ModelRecord",
    "NormalizedError",
    "Sensitivity",
    "StreamChunk",
    "StructuredInferenceResult",
    "adopt_generate",
    "cheap_ask_adopted",
    "compat_metrics_snapshot",
    "execute_governed_local_inference",
    "get_default_catalogue",
    "get_engine_registry",
    "load_inference_settings",
    "normalize_error",
    "profile_local_hardware",
    "prose_clean_adopted",
    "resolve_mode",
    "rollout_snapshot",
    "run_live_small_model_validation",
]
