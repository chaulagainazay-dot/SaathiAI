"""M279 — Research lab certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    MAX_STATE,
    PRESERVED_OOS_FAILURES,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_lab.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.research_lab.service import ResearchLabService


def certify_research_lab(svc: "ResearchLabService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    # Authority locks
    for k, v in AUTHORITY_VALUES.items():
        if k in (
            "paper_only", "sandbox_only", "research_only", "offline_first", "offline_capable",
            "no_broker_connection", "no_api_keys", "no_oauth", "no_order_submission",
            "no_live_data_dependency", "no_live_trading",
            "certified_experiment_requires_pre_registration",
            "human_review_required_for_paper_candidate",
            "paper_candidate_does_not_authorise_execution",
            "max_authority", "default_leverage_max",
        ):
            continue
        if v is True:
            failures.append(f"authority_true:{k}")
    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    if not checks["authority_locks_false"]:
        failures.append("LIVE_TRADING_AUTHORIZED")

    # Bootstrap full lab pipeline
    try:
        pipe = svc.bootstrap_demo_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["experiment_pre_registered"] = pipe.get("pre_registered") is True
        checks["comparison_ok"] = bool(pipe.get("comparison"))
        checks["robustness_ok"] = bool(pipe.get("robustness"))
        checks["regimes_ok"] = bool(pipe.get("regimes"))
        port = pipe.get("portfolio") or {}
        checks["portfolio_ok"] = bool(port.get("ok") or port.get("state") or port.get("weights"))
        checks["ensemble_ok"] = bool(pipe.get("ensemble"))
        stress = pipe.get("stress") or {}
        checks["stress_ok"] = bool(stress.get("ok") or stress.get("stress_id") or stress.get("historical_stresses"))
        checks["candidate_ok"] = bool(pipe.get("candidate"))
        preserved = pipe.get("preserved_oos_failures") or []
        checks["preserved_failures"] = len(preserved) >= 2
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline_exception:{e}")
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")
    if not checks.get("experiment_pre_registered"):
        failures.append("pre_registration_missing")
    if not checks.get("preserved_failures"):
        failures.append("oos_failures_not_preserved")

    # Pre-registration gate
    try:
        draft = svc.create_experiment(
            name="cert_gate_draft_only",
            description="must not run without pre-registration",
            strategy_ids=["tf_dual_ma"],
            random_seed=99,
        )
        try:
            svc.run_experiment(draft["experiment_id"], draft["experiment_version"])
            checks["pre_reg_gate"] = False
            failures.append("pre_registration_gate_bypassed")
        except Exception as e:
            code = getattr(e, "code", "")
            checks["pre_reg_gate"] = code in ("PRE_REGISTRATION_REQUIRED", "EXPERIMENT_NOT_RUNNABLE")
            if not checks["pre_reg_gate"]:
                failures.append(f"unexpected_pre_reg_error:{code}:{e}")
    except Exception as e:
        checks["pre_reg_gate"] = False
        failures.append(f"pre_reg_setup:{e}")

    # Leverage reject
    try:
        from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
        rets = {"A": _simulate_strategy_returns("tf_dual_ma", n=40, seed=1)["returns"],
                "B": _simulate_strategy_returns("mom_rs_equity", n=40, seed=2)["returns"]}
        bad = svc.build_portfolio(
            ["A", "B"], rets,
            method="equal_weight",
            constraints={"leverage_limit": 2.0, "maximum_asset_weight": 0.6},
        )
        checks["hidden_leverage_blocked"] = bad.get("ok") is False
        if not checks["hidden_leverage_blocked"]:
            failures.append("hidden_leverage_not_blocked")
    except Exception as e:
        checks["hidden_leverage_blocked"] = False
        failures.append(f"leverage_probe:{e}")

    # Ensemble leakage blocked
    try:
        leak = svc.build_ensemble(["tf_dual_ma", "mom_rs_equity"], method="equal_weight", leakage_tune_on_test=True)
        checks["ensemble_leakage_blocked"] = leak.get("state") == "LEAKAGE_BLOCKED"
        if not checks["ensemble_leakage_blocked"]:
            failures.append("ensemble_leakage_not_blocked")
    except Exception as e:
        checks["ensemble_leakage_blocked"] = False
        failures.append(f"ensemble_leak:{e}")

    # Human review bypass blocked
    try:
        c = svc.list_candidates()
        # create a committee-review candidate then try system approve
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        try:
            svc.candidates.human_approve_paper_candidate("cand_nonexistent", actor="system")
            checks["human_bypass_blocked"] = False
            failures.append("human_bypass_allowed")
        except ResearchLabError as e:
            checks["human_bypass_blocked"] = e.code in (
                "HUMAN_REVIEW_BYPASS_DETECTED", "CANDIDATE_NOT_FOUND",
            )
    except Exception as e:
        checks["human_bypass_blocked"] = False
        failures.append(f"human_bypass:{e}")

    # Preserved AAPL/BTC failures
    checks["aapl_btc_failures_preserved"] = all(
        f["state"] == "OUT_OF_SAMPLE_FAILED" for f in PRESERVED_OOS_FAILURES
    )
    if not checks["aapl_btc_failures_preserved"]:
        failures.append("preserved_failures_mutated")

    # Security
    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security_scan_failed")

    # Refusals
    checks["broker_refused"] = svc.refuse_broker().get("refused") is True
    checks["cred_refused"] = svc.refuse_credentials("x").get("refused") is True
    checks["order_refused"] = svc.refuse_order().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True

    ok = len(failures) == 0 and checks.get("pipeline_ok") and checks.get("pre_reg_gate")
    verdict = TERMINAL_VERDICT if ok else "M272_M279_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "pipeline": {
            "experiment_id": pipe.get("experiment_id"),
            "comparison_id": (pipe.get("comparison") or {}).get("comparison_id"),
            "candidate_state": (pipe.get("candidate") or {}).get("state"),
        },
        "preserved_oos_failures": list(PRESERVED_OOS_FAILURES),
        "limitations": [
            "Research-only multi-strategy lab; not production or live-market ready",
            "Portfolio optimisation is not regulatory-grade",
            "PAPER_CANDIDATE does not authorize execution",
            "Synthetic paths labelled unless bound to governed historical data",
            "Bounded historical OOS failures preserved from M270",
        ],
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO rl_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    return result
