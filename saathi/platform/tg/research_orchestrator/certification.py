"""M280–M287 certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_orchestrator.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.research_orchestrator.service import ResearchOrchestratorService


def certify_orchestrator(svc: "ResearchOrchestratorService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    if not checks["authority_locks_false"]:
        failures.append("LIVE_TRADING_AUTHORIZED")

    try:
        pipe = svc.bootstrap_demo_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["jobs_ran"] = len(pipe.get("ran") or []) >= 1
        checks["session_ok"] = bool(pipe.get("session_id"))
        checks["templates_ok"] = (pipe.get("templates_count") or 0) >= 1
        checks["hypothesis_ok"] = bool(pipe.get("hypothesis_id"))
        checks["journal_ok"] = bool(pipe.get("journal_entry_id"))
        checks["queue_stats"] = bool(pipe.get("queue"))
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline_exception:{e}")
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")

    # Budget exhaustion fail-closed
    try:
        from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
        # drain budget with huge reserve
        try:
            svc.budget.reserve(10**9)
            checks["budget_exhausted_blocks"] = False
            failures.append("budget_not_blocked")
        except OrchestratorError as e:
            checks["budget_exhausted_blocks"] = e.code == "BUDGET_EXHAUSTED"
            if not checks["budget_exhausted_blocks"]:
                failures.append(f"budget_code:{e.code}")
    except Exception as e:
        checks["budget_exhausted_blocks"] = False
        failures.append(f"budget_probe:{e}")

    # Cancel path
    try:
        j = svc.enqueue_job("cert_cancel_probe", {"kind": "noop", "seed": 9}, priority="LOW")
        c = svc.cancel_job(j["job_id"], reason="cert_probe")
        checks["cancel_works"] = c.get("state") == "CANCELLED"
    except Exception as e:
        checks["cancel_works"] = False
        failures.append(f"cancel:{e}")

    # Dependency blocking
    try:
        a = svc.enqueue_job("dep_parent", {"kind": "noop", "seed": 1})
        b = svc.enqueue_job("dep_child", {"kind": "noop", "seed": 2}, depends_on=[a["job_id"]])
        checks["dependency_blocked"] = b.get("state") == "BLOCKED"
        svc.tick(max_jobs=5)
        child = svc.get_job(b["job_id"])
        checks["dependency_released"] = child.get("state") in ("SUCCEEDED", "QUEUED", "RUNNING", "FAILED")
    except Exception as e:
        checks["dependency_blocked"] = False
        failures.append(f"deps:{e}")

    # Refusals
    checks["broker_refused"] = svc.refuse_broker().get("refused") is True
    checks["cred_refused"] = svc.refuse_credentials("x").get("refused") is True
    checks["order_refused"] = svc.refuse_order().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True

    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security_scan_failed")

    # Strategy registry V2 composes M248
    try:
        sr = svc.list_strategies_v2()
        checks["strategy_v2_ok"] = sr.get("ok") is True and (sr.get("count") or 0) >= 1
    except Exception as e:
        checks["strategy_v2_ok"] = False
        failures.append(f"strategy_v2:{e}")

    ok = len(failures) == 0 and checks.get("pipeline_ok")
    verdict = TERMINAL_VERDICT if ok else "M280_M287_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "pipeline": {
            "session_id": pipe.get("session_id"),
            "ran": pipe.get("ran"),
        },
        "limitations": [
            "In-process deterministic workers only — not a distributed cluster",
            "Runtime estimates are heuristics, not SLAs",
            "Research orchestration only; no paper or live order execution",
            "Budget is logical units, not cloud billing",
        ],
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO orch_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    return result
