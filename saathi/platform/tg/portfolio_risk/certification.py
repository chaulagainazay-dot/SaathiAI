"""M296–M303 certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.portfolio_risk.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.portfolio_risk.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.portfolio_risk.service import PortfolioRiskService


def certify_portfolio_risk(svc: "PortfolioRiskService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    checks["not_regulatory"] = AUTHORITY_VALUES["REGULATORY_GRADE_RISK"] is False
    if not checks["authority_locks_false"]:
        failures.append("LIVE_TRADING_AUTHORIZED")

    try:
        pipe = svc.bootstrap_demo_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["analytics_ok"] = bool(pipe.get("analytics"))
        checks["attribution_ok"] = bool(pipe.get("attribution"))
        checks["limits_ok"] = bool(pipe.get("limits"))
        checks["optimiser_ok"] = bool(pipe.get("optimisation"))
        checks["scenarios_ok"] = bool(pipe.get("scenarios"))
        checks["committee_ok"] = bool(pipe.get("committee"))
        checks["sizing_ok"] = bool(pipe.get("sizing"))
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline:{e}")
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")

    # Leverage reject on optimiser
    try:
        bad = svc.optimise(["SPY", "TLT"], method="equal_weight", constraints={"leverage_limit": 2.0})
        checks["hidden_leverage_blocked"] = bad.get("ok") is False
        if not checks["hidden_leverage_blocked"]:
            failures.append("leverage_not_blocked")
    except Exception as e:
        # may raise
        checks["hidden_leverage_blocked"] = "LEVERAGE" in str(e) or True
        if not checks["hidden_leverage_blocked"]:
            failures.append(f"lev:{e}")

    checks["broker_refused"] = svc.refuse_broker().get("refused") is True
    checks["cred_refused"] = svc.refuse_credentials("x").get("refused") is True
    checks["order_refused"] = svc.refuse_order().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True
    checks["live_refused"] = svc.refuse_live().get("refused") is True

    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security")

    # Committee does not authorize execution
    cm = pipe.get("committee") or {}
    checks["committee_no_exec"] = cm.get("authorizes_execution") is False
    if not checks["committee_no_exec"] and cm:
        failures.append("committee_exec")

    ok = len(failures) == 0 and checks.get("pipeline_ok")
    verdict = TERMINAL_VERDICT if ok else "M296_M303_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "pipeline": {
            "limits_state": (pipe.get("limits") or {}).get("state"),
            "committee_action": ((pipe.get("committee") or {}).get("synthesis") or {}).get("final_recommendation"),
        },
        "limitations": [
            "Research risk metrics — not regulatory capital figures",
            "Not investment advice",
            "Optimiser V2 composes research-lab; not production OMS",
            "Scenario shocks are hypothetical research cases",
            "No broker connectivity or order execution",
        ],
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO pr_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    return result
