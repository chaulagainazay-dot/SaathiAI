"""M20.4 — Control Center engineering facet builder (read-only)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from saathi.engineering.read_model import build_engineering_status
from saathi.engineering.security import trading_guardian_isolation_report
from saathi.engineering.settings import load_settings
from saathi.engineering.store import EngineeringStore


def engineering_control_center_status(
    *,
    store_dir: Optional[str] = None,
    repository_root: Optional[str] = None,
) -> dict[str, Any]:
    """Build versioned engineering status for Control Center aggregation."""
    try:
        settings = load_settings(store_dir=store_dir or "")
        store = EngineeringStore(settings.store_path())
        # detect corrupt
        raw_sessions = store._read_json(store.sessions_path)
        corrupt = bool(raw_sessions.get("_corrupt"))
        sessions = [] if corrupt else store.list_sessions(active_only=False)
        readiness = None
        selection = None
        try:
            from saathi.engineering.readiness import check_repository_readiness
            from saathi.config import ROOT

            root = Path(repository_root or ROOT)
            readiness = check_repository_readiness(root, settings).to_dict()
        except Exception as e:
            readiness = {"state": "unavailable", "error": str(e)[:120]}
        try:
            from saathi.engineering.selector import select_candidate

            items = store.list_items()
            if items:
                selection = select_candidate(items).to_dict()
        except Exception:
            selection = None

        warnings: list[str] = []
        if corrupt:
            warnings.append("engineering_store_corrupt")
        if settings.repository_writes_enabled:
            warnings.append("writes_flag_enabled")
        if settings.commits_enabled:
            warnings.append("commits_flag_enabled")
        if settings.pushes_enabled:
            warnings.append("pushes_flag_enabled")

        status = build_engineering_status(
            settings=settings.to_dict(),
            sessions=sessions,
            readiness=readiness,
            selection=selection,
            store_corrupt=corrupt,
            security_warnings=warnings,
            trading_isolation=trading_guardian_isolation_report(),
        )
        from saathi.config import ROOT

        status["repository_identity"]["root"] = str(repository_root or ROOT)
        status["repository_identity"]["store_path"] = str(settings.store_path())
        # Flatten commonly requested facet fields for CC UI
        mon = status.get("monitoring_status") or {}
        act = mon.get("active_session") or {}
        flags = status.get("safety_flags") or {}
        status["facet_fields"] = {
            "orchestrator_enabled": flags.get("orchestrator_enabled"),
            "launch_enabled": flags.get("launch_enabled"),
            "writes_enabled": flags.get("writes_enabled"),
            "commits_enabled": flags.get("commits_enabled"),
            "pushes_enabled": flags.get("pushes_enabled"),
            "active_engineering_session": act.get("session_id"),
            "provider_adapter": act.get("adapter") or act.get("provider"),
            "repository_path": status["repository_identity"].get("root"),
            "branch": status["repository_identity"].get("branch"),
            "start_commit": act.get("start_commit") or act.get("head"),
            "current_commit": act.get("current_commit") or status["repository_identity"].get("head"),
            "candidate_backlog_item": (status.get("candidate") or {}).get("item_id"),
            "selected_score": (status.get("candidate") or {}).get("score"),
            "selected_rationale": (status.get("candidate") or {}).get("rationale"),
            "readiness_classification": (status.get("readiness") or {}).get("state"),
            "readiness_blockers": (status.get("readiness") or {}).get("blockers")
            or (status.get("readiness") or {}).get("reasons"),
            "current_phase": mon.get("phase"),
            "last_checkpoint": mon.get("last_checkpoint"),
            "heartbeat_age_sec": mon.get("heartbeat_age_sec"),
            "stall_status": mon.get("stall"),
            "retry_count": mon.get("retry_count"),
            "latest_validation": (status.get("validation_summary") or {}).get("latest"),
            "required_validation_failures": (status.get("validation_summary") or {}).get(
                "required_failures"
            ),
            "optional_validation_skips": (status.get("validation_summary") or {}).get(
                "optional_skips"
            ),
            "branch_change_detected": "branch_changed"
            in ((status.get("integrity_summary") or {}).get("mutations") or []),
            "dirty_tree_detected": bool(
                (status.get("readiness") or {}).get("dirty")
                or (status.get("readiness") or {}).get("is_dirty")
            ),
            "observed_file_scope": act.get("changed_files") or [],
            "stop_policy_recommendation": status.get("stop_policy_recommendation"),
            "final_session_status": status.get("final_session_status") or act.get("status"),
            "handoff_readiness": (status.get("handoff_summary") or {}).get("ready"),
            "security_warnings": status.get("security_warnings"),
            "trading_guardian_isolation": status.get("trading_guardian_isolation"),
            "mode": act.get("mode") or "n/a",
            "integrity_ok": (status.get("integrity_summary") or {}).get("ok"),
        }
        return status
    except Exception as e:
        return {
            "schema_version": "engineering_status.v1",
            "lifecycle_state": "unavailable",
            "error": str(e)[:200],
            "read_only": True,
            "facet": "engineering_orchestrator",
            "trading_guardian_isolation": {"unengaged": True},
            "safety_flags": {
                "orchestrator_enabled": False,
                "writes_enabled": False,
                "commits_enabled": False,
                "pushes_enabled": False,
            },
        }
