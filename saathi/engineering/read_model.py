"""M20.4 — Versioned Engineering Control Center read model.

Consumable by Control Center aggregator; never parses terminal output.
Secrets and full prompts are never included.
"""
from __future__ import annotations

import time
from typing import Any, Optional

SCHEMA_VERSION = "engineering_status.v1"


def _redact_session(sess: dict[str, Any]) -> dict[str, Any]:
    """Strip sensitive fields for Control Center display."""
    if not sess:
        return {}
    keep = {
        "session_id", "status", "item_id", "task_id", "adapter", "provider",
        "started_at", "updated_at", "ended_at", "branch", "head", "start_commit",
        "current_commit", "mode", "write_enabled", "phase", "last_checkpoint",
        "last_heartbeat", "pid", "stop_reason", "retry_count", "lease_until",
        "owner_pid", "integrity_ok", "mutations", "handoff_ready",
        "validation_summary", "readiness_state", "score", "rationale",
        "prompt_fingerprint", "approval_id", "quarantine_reason",
    }
    out = {k: sess.get(k) for k in keep if k in sess}
    # never leak env, tokens, full prompt, secrets
    for ban in ("prompt", "env", "token", "secret", "api_key", "stdout_full", "stderr_full"):
        out.pop(ban, None)
    return out


def build_engineering_status(
    *,
    settings: dict[str, Any],
    sessions: list[dict[str, Any]],
    readiness: Optional[dict[str, Any]] = None,
    selection: Optional[dict[str, Any]] = None,
    store_corrupt: bool = False,
    security_warnings: Optional[list[str]] = None,
    trading_isolation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Stable versioned schema for Control Center facet."""
    active = [
        s for s in sessions
        if s.get("status") in {
            "pending", "starting", "running", "stalled",
            "awaiting_approval", "paused",
        }
    ]
    active_sess = active[0] if active else None
    now = time.time()
    hb_age = None
    stall = False
    if active_sess:
        hb = float(active_sess.get("last_heartbeat") or active_sess.get("started_at") or 0)
        if hb:
            hb_age = round(now - hb, 2)
            stall = hb_age > float(settings.get("stall_timeout_sec") or 600)

    # Flags — never include secret values
    flags = {
        "orchestrator_enabled": bool(settings.get("orchestrator_enabled")),
        "launch_enabled": bool(settings.get("agent_launching_enabled")),
        "writes_enabled": bool(settings.get("repository_writes_enabled")),
        "commits_enabled": bool(settings.get("commits_enabled")),
        "pushes_enabled": bool(settings.get("pushes_enabled")),
        "merge_allowed": False,
        "deploy_allowed": False,
        "trading_allowed": False,
    }

    lifecycle = "disabled"
    if not flags["orchestrator_enabled"]:
        lifecycle = "disabled"
    elif store_corrupt:
        lifecycle = "store_corrupt"
    elif active_sess and active_sess.get("status") == "quarantined":
        lifecycle = "quarantined"
    elif active_sess:
        lifecycle = str(active_sess.get("status") or "running")
    else:
        lifecycle = "idle"

    candidate = {}
    if selection:
        candidate = {
            "item_id": selection.get("item_id") or (selection.get("item") or {}).get("item_id"),
            "score": selection.get("score"),
            "rationale": selection.get("rationale") or selection.get("reasons"),
            "title": (selection.get("item") or {}).get("title"),
        }

    redacted_active = _redact_session(active_sess or {})
    integrity = {
        "ok": (active_sess or {}).get("integrity_ok"),
        "mutations": (active_sess or {}).get("mutations") or [],
        "start_commit": (active_sess or {}).get("start_commit") or (active_sess or {}).get("head"),
        "current_commit": (active_sess or {}).get("current_commit"),
    }

    val = (active_sess or {}).get("validation_summary") or {}
    handoff = {
        "ready": bool((active_sess or {}).get("handoff_ready")),
        "path": (active_sess or {}).get("handoff_path") or "",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "source_session_ids": [s.get("session_id") for s in sessions if s.get("session_id")],
        "repository_identity": {
            "root": settings.get("store_path") and None,  # filled by caller
            "branch": (active_sess or {}).get("branch") or (readiness or {}).get("branch"),
            "head": (active_sess or {}).get("head") or (readiness or {}).get("head"),
        },
        "lifecycle_state": lifecycle,
        "safety_flags": flags,
        "monitoring_status": {
            "active_session": redacted_active or None,
            "heartbeat_age_sec": hb_age,
            "stall": stall,
            "retry_count": (active_sess or {}).get("retry_count", 0),
            "phase": (active_sess or {}).get("phase") or "",
            "last_checkpoint": (active_sess or {}).get("last_checkpoint"),
        },
        "readiness": readiness or {"state": "unknown"},
        "candidate": candidate,
        "validation_summary": {
            "latest": val,
            "required_failures": val.get("required_failures") or [],
            "optional_skips": val.get("optional_skips") or [],
        },
        "integrity_summary": integrity,
        "handoff_summary": handoff,
        "stop_policy_recommendation": (active_sess or {}).get("stop_recommendation") or "",
        "final_session_status": (active_sess or {}).get("status") if not active else None,
        "security_warnings": list(security_warnings or []),
        "trading_guardian_isolation": trading_isolation or {
            "unengaged": True,
            "engineering_can_execute_trades": False,
        },
        "store_corrupt": store_corrupt,
        "facet": "engineering_orchestrator",
        "read_only": True,  # Control Center facet is always read-only
    }
