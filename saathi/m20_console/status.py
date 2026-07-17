"""M20.7 — Unified read-only M20 console status.

Aggregates Engineering Orchestrator + Governed Inference snapshots without
merging their stores, routers, or gateways.
"""
from __future__ import annotations

import time
from typing import Any

from saathi.m20_console.flags import disable_procedure, domains_isolated, flag_snapshot


def engineering_snapshot() -> dict[str, Any]:
    try:
        from saathi.engineering.settings import load_settings
        from saathi.engineering.store import EngineeringStore

        s = load_settings()
        store = EngineeringStore(s.store_path())
        sessions = store.list_sessions(active_only=False)
        active = store.list_sessions(active_only=True)
        ledger = {}
        try:
            ledger = store.ledger().census()
        except Exception as e:
            ledger = {"error": type(e).__name__}
        return {
            "domain": "engineering",
            "ok": True,
            "orchestrator_enabled": s.orchestrator_enabled,
            "launch_enabled": s.agent_launching_enabled,
            "writes_enabled": s.repository_writes_enabled,
            "commits_enabled": s.commits_enabled,
            "pushes_enabled": s.pushes_enabled,
            "max_active_sessions": s.max_active_sessions,
            "backlog_count": len(store.list_items()),
            "session_count": len(sessions),
            "active_sessions": len(active),
            "ledger": ledger,
            "hard_denials": {
                "merge": s.merge_allowed,
                "deploy": s.deploy_allowed,
                "force_push": s.force_push_allowed,
                "trading": s.trading_allowed,
            },
        }
    except Exception as e:
        return {"domain": "engineering", "ok": False, "error": type(e).__name__}


def inference_snapshot() -> dict[str, Any]:
    try:
        from saathi.inference.caller_rollout import rollout_snapshot
        from saathi.inference.config import load_inference_settings
        from saathi.inference.hardware import profile_local_hardware

        settings = load_inference_settings()
        hw = profile_local_hardware()
        engines = []
        models = []
        try:
            from saathi.inference.certification import discover_engines, discover_models
            engines = [e.to_dict() for e in discover_engines(settings)]
            models = [m.to_dict() for m in discover_models(settings) if m.model_id]
        except Exception as e:
            engines = [{"error": type(e).__name__}]
        cert = {
            "last_live_status": "unknown",
            "suite": "m20.6.cert.suite.v1",
            "cli": "python -m saathi.inference.certification run",
        }
        m21 = {}
        try:
            from saathi.inference.prod_config import validate_production_config
            from saathi.inference.provider_policy import provider_policy_snapshot
            try:
                from saathi.inference.provider_governance import governance_snapshot
                m21_2_gov = governance_snapshot()
            except Exception:
                m21_2_gov = {"ok": False}

            m21 = {
                "prod_config_posture": validate_production_config(settings).posture,
                "prod_config_ok": validate_production_config(settings).ok,
                "provider_kill_all": provider_policy_snapshot().get("kill_all_active"),
                "cli": "python -m saathi.inference.prod_config bundle",
            }
            m21["provider_governance"] = {
                "schema": m21_2_gov.get("schema"),
                "kill_all": m21_2_gov.get("kill_all"),
                "production_certified": False,
                "provider_count": len(m21_2_gov.get("providers") or []),
                "cli": "python -m saathi.inference.provider_governance",
            }
        except Exception as e:
            m21 = {"error": type(e).__name__}
        return {
            "domain": "inference",
            "ok": True,
            "enabled": settings.enabled,
            "gateway_enabled": settings.gateway_enabled,
            "allow_cloud_fallback": settings.allow_cloud_fallback,
            "default_engine": settings.default_engine,
            "max_concurrent_local": settings.max_concurrent_local,
            "max_prompt_chars": settings.max_prompt_chars,
            "max_output_tokens": settings.max_output_tokens,
            "rollout": rollout_snapshot(),
            "hardware": {
                "available_memory_gb": hw.available_memory_gb,
                "total_memory_gb": hw.total_memory_gb,
                "recommended_max_model_size_b": hw.recommended_max_model_size_b,
                "warnings": list(hw.warnings)[:8],
            },
            "engines": engines,
            "models_installed_count": len(models),
            "models_sample": models[:8],
            "certification": cert,
            "m21_0": m21,
            "m21_2": m21.get("provider_governance") if isinstance(m21, dict) else None,
            "production_certified": False,
        }
    except Exception as e:
        return {"domain": "inference", "ok": False, "error": type(e).__name__}


def trading_guardian_snapshot() -> dict[str, Any]:
    try:
        from saathi.engineering.security import trading_guardian_isolation_report
        rep = trading_guardian_isolation_report()
        return {
            "domain": "trading_guardian",
            "engaged": False,
            "isolation": rep,
            "note": "M20 console never engages TG",
        }
    except Exception as e:
        return {"domain": "trading_guardian", "engaged": False, "error": type(e).__name__}


def cli_discovery() -> dict[str, Any]:
    """Operator entrypoints (discovery only)."""
    return {
        "m20_console": "python -m saathi.m20_console",
        "engineering": "python -m saathi.engineering",
        "engineering_control_center": "python -m saathi.engineering control-center",
        "inference_cert": "python -m saathi.inference.certification",
        "inference_discover": "python -m saathi.inference.certification discover",
        "inference_prod_config": "python -m saathi.inference.prod_config",
        "ops": "python -m saathi.ops",
        "control_center": "python -m saathi.control_center.cli",
    }


def m20_console_status() -> dict[str, Any]:
    """Single read-only aggregation for operators and Control Center."""
    eng = engineering_snapshot()
    inf = inference_snapshot()
    flags = flag_snapshot()
    # health rollup
    issues = []
    if eng.get("ok") and eng.get("writes_enabled"):
        issues.append("engineering_writes_enabled")
    if inf.get("ok") and inf.get("allow_cloud_fallback"):
        issues.append("inference_cloud_fallback_enabled")
    if flags.get("security_sensitive_enabled"):
        issues.append("security_sensitive_flags_on")
    if inf.get("ok") and (inf.get("hardware") or {}).get("available_memory_gb", 99) < 2.0:
        issues.append("memory_pressure")
    if inf.get("ok") and int(inf.get("models_installed_count") or 0) == 0:
        issues.append("no_installed_local_models")

    posture = "ok"
    if any(x in issues for x in ("engineering_writes_enabled", "inference_cloud_fallback_enabled")):
        posture = "attention"
    if issues:
        posture = "degraded" if posture == "ok" else posture

    return {
        "schema": "m20_console_status.v1",
        "observed_at": time.time(),
        "posture": posture,
        "issues": issues,
        "domains_isolated": domains_isolated(),
        "flags": flags,
        "disable": disable_procedure(),
        "cli": cli_discovery(),
        "engineering": eng,
        "inference": inf,
        "trading_guardian": trading_guardian_snapshot(),
        "series": {
            "completed": [
                "M20.0", "M20.1", "M20.2", "M20.3", "M20.4", "M20.5",
                "M20.7", "M20.9", "M20.10",
            ],
            "blocked": ["M20.6_live"],
            "intentionally_skipped": ["M20.8"],
            "current": None,
            "next": "M21_not_started",
            "verdict": "M20 COMPLETE WITH LIMITATIONS",
            "plan": "docs/M20_SERIES_PLAN_M20_5_TO_M20_10.md",
            "closure": "docs/M20_10_CLOSURE.md",
            "master_loop": "docs/M20_MASTER_AUTONOMOUS_ENGINEERING_LOOP.md",
        },
    }


def inference_control_center_facet() -> dict[str, Any]:
    """Read-only inference facet for Control Center (never executes generation)."""
    snap = inference_snapshot()
    return {
        "schema_version": "inference_status.v1",
        "enabled": snap.get("enabled"),
        "gateway_enabled": snap.get("gateway_enabled"),
        "cloud_fallback": snap.get("allow_cloud_fallback"),
        "rollout_defaults_legacy": (
            (snap.get("rollout") or {}).get("resolved") or {}
        ),
        "models_installed_count": snap.get("models_installed_count"),
        "hardware_available_gb": (snap.get("hardware") or {}).get("available_memory_gb"),
        "engines": snap.get("engines"),
        "executes_inference": False,
        "note": "M20.7 facet is observational only",
    }
