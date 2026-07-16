"""Inference / OpenJarvis-compat configuration (default-safe).

Uses environment variables so we do not introduce a second config framework.
Mirrors the suggested TOML shape from the M20.1 brief.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class InferenceSettings:
    """Default-safe inference settings.

    All new behaviour is off unless explicitly enabled.
    """

    # [openjarvis_compat] — conceptual flag; does not start OpenJarvis
    openjarvis_compat_enabled: bool = False

    # [inference]
    enabled: bool = False
    default_engine: str = "ollama"
    allow_cloud_fallback: bool = False
    health_check_interval_seconds: int = 300
    request_timeout_seconds: float = 60.0
    max_retries: int = 1  # bounded; 0 = no retry after first attempt
    discovery_enabled: bool = False

    # [hardware]
    auto_detect_hardware: bool = True
    disk_warning_gb: float = 25.0
    memory_safety_margin_gb: float = 2.0

    # [benchmarks]
    benchmarks_enabled: bool = False
    store_benchmark_results: bool = True

    # [skills.third_party]
    third_party_skills_enabled: bool = False
    require_skill_review: bool = True
    skill_sandbox_required: bool = True

    # [learning.routing]
    learning_routing_mode: str = "advisory"  # advisory | off (active forbidden without gates)

    def cloud_fallback_allowed(self, *, privacy_local_only: bool = False) -> bool:
        if privacy_local_only:
            return False
        return self.allow_cloud_fallback


def load_inference_settings() -> InferenceSettings:
    """Load settings from environment (SaathiOS convention)."""
    mode = (os.getenv("SAATHI_LEARNING_ROUTING_MODE") or "advisory").strip().lower()
    if mode not in {"advisory", "off"}:
        # Never default to active self-learned routing
        mode = "advisory"
    return InferenceSettings(
        openjarvis_compat_enabled=_env_bool("SAATHI_OPENJARVIS_COMPAT", False),
        enabled=_env_bool("SAATHI_INFERENCE_ENABLED", False),
        default_engine=(os.getenv("SAATHI_DEFAULT_ENGINE") or "ollama").strip() or "ollama",
        allow_cloud_fallback=_env_bool("SAATHI_ALLOW_CLOUD_FALLBACK", False),
        health_check_interval_seconds=_env_int("SAATHI_ENGINE_HEALTH_INTERVAL", 300),
        request_timeout_seconds=_env_float("SAATHI_INFERENCE_TIMEOUT", 60.0),
        max_retries=max(0, min(_env_int("SAATHI_INFERENCE_MAX_RETRIES", 1), 3)),
        discovery_enabled=_env_bool("SAATHI_ENGINE_DISCOVERY", False),
        auto_detect_hardware=_env_bool("SAATHI_HARDWARE_AUTO_DETECT", True),
        disk_warning_gb=_env_float("SAATHI_DISK_WARNING_GB", 25.0),
        memory_safety_margin_gb=_env_float("SAATHI_MEMORY_SAFETY_MARGIN_GB", 2.0),
        benchmarks_enabled=_env_bool("SAATHI_BENCHMARKS_ENABLED", False),
        store_benchmark_results=_env_bool("SAATHI_BENCHMARKS_STORE", True),
        third_party_skills_enabled=_env_bool("SAATHI_THIRD_PARTY_SKILLS", False),
        require_skill_review=_env_bool("SAATHI_SKILL_REQUIRE_REVIEW", True),
        skill_sandbox_required=_env_bool("SAATHI_SKILL_SANDBOX_REQUIRED", True),
        learning_routing_mode=mode,
    )
