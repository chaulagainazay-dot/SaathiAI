"""SaathiOS unified inference runtime (M20.1 Slice A).

OpenJarvis-informed, SaathiOS-native. This package provides:

* ``InferenceEngine`` contract (generate/stream/health/list_models/…)
* engine registration and optional discovery
* model catalogue with capability provenance
* local hardware capability profile (M2 8 GB aware)
* bounded benchmark harness
* observation feed into the existing ``ModelRouter`` (which remains authoritative)

Disabled by default. Does **not** replace ModelRouter, ExecutionGateway,
mission engine, memory governance, or Trading Guardian.
"""
from __future__ import annotations

from saathi.inference.catalogue import (
    CapabilityProvenance,
    ModelCatalogue,
    ModelRecord,
    get_default_catalogue,
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

__all__ = [
    "CapabilityProvenance",
    "EngineCapabilities",
    "EngineError",
    "EngineRegistry",
    "EngineTimeoutError",
    "EngineUnhealthyError",
    "GenerateResult",
    "HardwareProfile",
    "InferenceEngine",
    "InferenceError",
    "InferenceSettings",
    "ModelCatalogue",
    "ModelRecord",
    "NormalizedError",
    "StreamChunk",
    "get_default_catalogue",
    "get_engine_registry",
    "load_inference_settings",
    "normalize_error",
    "profile_local_hardware",
]
