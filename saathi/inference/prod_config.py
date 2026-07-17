"""M21.0 — Production configuration schema and validation.

Validates ``InferenceSettings`` + provider policy posture for safe defaults.
Does **not** claim production certification (M21.3 / M24). Does **not**
download models, call paid APIs, or engage Trading Guardian.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Sequence

from saathi.inference.config import InferenceSettings, load_inference_settings
from saathi.inference.path_inventory import path_inventory_snapshot
from saathi.inference.provider_policy import (
    disable_provider_commands,
    provider_policy_snapshot,
)


def _m21_1_bundle() -> dict:
    try:
        from saathi.inference.bypass_guard import scan_repository
        from saathi.inference.caller_policy import caller_policy_snapshot
        from saathi.inference.residual_paths import residual_paths_snapshot

        return {
            "caller_policy": caller_policy_snapshot(),
            "residual_paths": residual_paths_snapshot(),
            "bypass_guard": {
                "cli": "python -m saathi.inference.bypass_guard",
                "ok_hint": "run scan in CI/tests",
            },
        }
    except Exception as e:
        return {"error": type(e).__name__}


SCHEMA_VERSION = "m21.0.prod_config.v1"


@dataclass
class ConfigFinding:
    code: str
    severity: str  # ok | warning | blocking
    message: str
    field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductionConfigReport:
    schema: str = SCHEMA_VERSION
    milestone: str = "M21.0"
    ok: bool = True
    blocking: int = 0
    warnings: int = 0
    findings: list[ConfigFinding] = field(default_factory=list)
    settings_summary: dict[str, Any] = field(default_factory=dict)
    posture: str = "pilot_safe"  # pilot_safe | attention | unsafe
    production_certified: bool = False  # always False in M21.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "milestone": self.milestone,
            "ok": self.ok,
            "blocking": self.blocking,
            "warnings": self.warnings,
            "findings": [f.to_dict() for f in self.findings],
            "settings_summary": self.settings_summary,
            "posture": self.posture,
            "production_certified": self.production_certified,
            "notes": self.notes,
        }


def _settings_summary(s: InferenceSettings) -> dict[str, Any]:
    """Privacy-safe summary — never secrets."""
    return {
        "enabled": s.enabled,
        "gateway_enabled": s.gateway_enabled,
        "allow_cloud_fallback": s.allow_cloud_fallback,
        "default_engine": s.default_engine,
        "request_timeout_seconds": s.request_timeout_seconds,
        "max_retries": s.max_retries,
        "max_prompt_chars": s.max_prompt_chars,
        "max_output_tokens": s.max_output_tokens,
        "max_concurrent_local": s.max_concurrent_local,
        "min_available_memory_gb": s.min_available_memory_gb,
        "local_engine_allowlist": list(s.local_engine_allowlist),
        "allowed_ollama_hosts": list(s.allowed_ollama_hosts),
        "ollama_base_url_is_loopback": _is_loopback_url(s.ollama_base_url),
        "learning_routing_mode": s.learning_routing_mode,
        "third_party_skills_enabled": s.third_party_skills_enabled,
        "skill_sandbox_required": s.skill_sandbox_required,
        "openjarvis_compat_enabled": s.openjarvis_compat_enabled,
        "live_health_probe_enabled": s.live_health_probe_enabled,
    }


def _is_loopback_url(url: str) -> bool:
    u = (url or "").lower()
    return any(h in u for h in ("127.0.0.1", "localhost", "[::1]", "://::1"))


def validate_production_config(
    settings: Optional[InferenceSettings] = None,
) -> ProductionConfigReport:
    """Validate settings against M21.0 production-safe schema.

    Returns ok=False only on blocking misconfigurations. Enabling pilot flags
    is a **warning**, not blocking — operators may opt in deliberately.
    """
    s = settings or load_inference_settings()
    report = ProductionConfigReport(
        settings_summary=_settings_summary(s),
        notes=[
            "M21.0 validates configuration posture only",
            "production_certified is always false until M24/M21.3 gates",
            "Live model cert (M20.6) remains environment-dependent",
        ],
        production_certified=False,
    )

    def add(code: str, severity: str, message: str, field: str = "") -> None:
        report.findings.append(ConfigFinding(code, severity, message, field))
        if severity == "blocking":
            report.blocking += 1
        elif severity == "warning":
            report.warnings += 1

    # ── Hard safety (blocking) ──────────────────────────────────────────
    if s.learning_routing_mode not in {"advisory", "off"}:
        add(
            "learning_routing_active",
            "blocking",
            f"learning_routing_mode={s.learning_routing_mode!r} forbidden without gates",
            "learning_routing_mode",
        )

    if s.max_retries > 3:
        add(
            "max_retries_unbounded",
            "blocking",
            f"max_retries={s.max_retries} exceeds hard cap 3",
            "max_retries",
        )

    if s.max_concurrent_local > 2:
        add(
            "concurrency_too_high",
            "blocking",
            f"max_concurrent_local={s.max_concurrent_local} exceeds hard cap 2 (8 GB host)",
            "max_concurrent_local",
        )

    if s.max_output_tokens > 8192:
        add(
            "output_tokens_too_high",
            "blocking",
            f"max_output_tokens={s.max_output_tokens} exceeds hard cap 8192",
            "max_output_tokens",
        )

    if s.max_prompt_chars > 200_000:
        add(
            "prompt_chars_too_high",
            "blocking",
            f"max_prompt_chars={s.max_prompt_chars} exceeds hard cap 200000",
            "max_prompt_chars",
        )

    if s.request_timeout_seconds <= 0 or s.request_timeout_seconds > 600:
        add(
            "timeout_out_of_range",
            "blocking",
            f"request_timeout_seconds={s.request_timeout_seconds} not in (0, 600]",
            "request_timeout_seconds",
        )

    if s.third_party_skills_enabled and not s.skill_sandbox_required:
        add(
            "skills_without_sandbox",
            "blocking",
            "third_party skills enabled without sandbox requirement",
            "skill_sandbox_required",
        )

    if s.gateway_enabled and not s.enabled:
        add(
            "gateway_without_master",
            "blocking",
            "SAATHI_INFERENCE_GATEWAY_ENABLED without SAATHI_INFERENCE_ENABLED",
            "gateway_enabled",
        )

    if "ollama" not in s.local_engine_allowlist and s.default_engine == "ollama":
        add(
            "default_engine_not_allowlisted",
            "blocking",
            "default_engine=ollama but ollama not in local_engine_allowlist",
            "local_engine_allowlist",
        )

    # Non-loopback ollama with inference on → blocking for production posture
    if s.enabled and s.gateway_enabled and not _is_loopback_url(s.ollama_base_url):
        hosts_ok = any(
            h in (s.ollama_base_url or "").lower()
            for h in s.allowed_ollama_hosts
        )
        if not hosts_ok:
            add(
                "ollama_host_not_allowlisted",
                "blocking",
                "ollama_base_url host not in allowed_ollama_hosts",
                "ollama_base_url",
            )

    # ── Soft posture (warnings) ─────────────────────────────────────────
    if s.allow_cloud_fallback:
        add(
            "cloud_fallback_enabled",
            "warning",
            "SAATHI_ALLOW_CLOUD_FALLBACK is enabled — cloud escape risk",
            "allow_cloud_fallback",
        )

    if s.enabled:
        add(
            "inference_master_on",
            "warning",
            "SAATHI_INFERENCE_ENABLED is on (pilot opt-in)",
            "enabled",
        )

    if s.gateway_enabled:
        add(
            "gateway_on",
            "warning",
            "SAATHI_INFERENCE_GATEWAY_ENABLED is on (pilot opt-in)",
            "gateway_enabled",
        )

    if s.live_health_probe_enabled:
        add(
            "live_health_on",
            "warning",
            "live health probes enabled — may contact local engine",
            "live_health_probe_enabled",
        )

    if s.openjarvis_compat_enabled:
        add(
            "oj_compat_on",
            "warning",
            "OpenJarvis compat flag on (concepts only; no OJ process expected)",
            "openjarvis_compat_enabled",
        )

    if s.default_engine not in s.local_engine_allowlist and s.default_engine != "ollama":
        add(
            "default_engine_unusual",
            "warning",
            f"default_engine={s.default_engine!r} outside common local allowlist",
            "default_engine",
        )

    # Safe defaults check (informational ok findings)
    if (
        not s.enabled
        and not s.gateway_enabled
        and not s.allow_cloud_fallback
        and s.learning_routing_mode in {"advisory", "off"}
    ):
        add(
            "safe_defaults",
            "ok",
            "Master inference flags off; cloud fallback off; learning advisory/off",
            "",
        )

    report.ok = report.blocking == 0
    if report.blocking:
        report.posture = "unsafe"
    elif report.warnings:
        report.posture = "attention"
    else:
        report.posture = "pilot_safe"
    return report


def production_config_bundle(
    settings: Optional[InferenceSettings] = None,
) -> dict[str, Any]:
    """Full M21.0 operator bundle: validate + policy + inventory + disable."""
    s = settings or load_inference_settings()
    report = validate_production_config(s)
    return {
        "schema": "m21.0.production_bundle.v1",
        "milestone": "M21.0",
        "validation": report.to_dict(),
        "provider_policy": provider_policy_snapshot(),
        "path_inventory": path_inventory_snapshot(),
        "disable": disable_provider_commands(),
        "authorities": {
            "model_router": "saathi.model_router.ModelRouter",
            "inference_package": "saathi.inference",
            "execution_gateway": "saathi.execution (ModelGateway path)",
            "second_model_router": False,
            "second_inference_package": False,
            "trading_guardian_engaged": False,
        },
        "m21_1": _m21_1_bundle(),
        "m21_4": {
            "runtime_gate": "python -m saathi.inference.runtime_gate",
            "note": "M21.4 consolidated production-configuration gate; production_certified remains false without live evidence",
        },
        "cli": {
            "validate": "python -m saathi.inference.prod_config validate",
            "inventory": "python -m saathi.inference.prod_config inventory",
            "policy": "python -m saathi.inference.prod_config policy",
            "bundle": "python -m saathi.inference.prod_config bundle",
            "disable": "python -m saathi.inference.prod_config disable",
            "bypass_guard": "python -m saathi.inference.bypass_guard",
            "runtime_gate": "python -m saathi.inference.runtime_gate",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(
            "M21.0 production config CLI\n"
            "  validate   validate InferenceSettings posture\n"
            "  inventory  residual call-path inventory\n"
            "  policy     provider policy + kill switches\n"
            "  disable    provider disable commands\n"
            "  bundle     full operator bundle\n"
        )
        return 0
    cmd = argv[0]
    if cmd == "validate":
        print(json.dumps(validate_production_config().to_dict(), indent=1))
        return 0 if validate_production_config().ok else 2
    if cmd == "inventory":
        print(json.dumps(path_inventory_snapshot(), indent=1))
        return 0
    if cmd == "policy":
        print(json.dumps(provider_policy_snapshot(), indent=1))
        return 0
    if cmd == "disable":
        print(json.dumps(disable_provider_commands(), indent=1))
        return 0
    if cmd == "bundle":
        print(json.dumps(production_config_bundle(), indent=1, default=str))
        return 0
    if cmd in ("guard", "bypass-guard", "bypass_guard"):
        from saathi.inference.bypass_guard import scan_repository

        rep = scan_repository()
        print(json.dumps(rep, indent=1))
        return 0 if rep.get("ok") else 2
    if cmd in ("callers", "caller-policy"):
        from saathi.inference.caller_policy import caller_policy_snapshot

        print(json.dumps(caller_policy_snapshot(), indent=1))
        return 0
    if cmd in ("residual", "residuals"):
        from saathi.inference.residual_paths import residual_paths_snapshot

        print(json.dumps(residual_paths_snapshot(), indent=1))
        return 0
    print(json.dumps({"error": "unknown_command", "cmd": cmd}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
