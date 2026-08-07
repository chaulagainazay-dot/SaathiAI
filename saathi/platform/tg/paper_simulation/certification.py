"""M288–M295 certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.paper_simulation.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.paper_simulation.service import PaperSimulationService


def certify_paper_simulation(svc: "PaperSimulationService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    checks["real_exchange_false"] = AUTHORITY_VALUES["REAL_EXCHANGE_AUTHORIZED"] is False
    if not checks["authority_locks_false"]:
        failures.append("LIVE_TRADING_AUTHORIZED")

    try:
        pipe = svc.bootstrap_demo_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["portfolio_created"] = bool(pipe.get("portfolio_id"))
        checks["market_order_filled"] = bool(pipe.get("market_fill"))
        checks["limit_order_ok"] = bool(pipe.get("limit_order_id"))
        checks["order_book_ok"] = bool(pipe.get("order_book"))
        checks["cash_ledger_ok"] = (pipe.get("cash_entries") or 0) >= 1
        checks["fills_audited"] = (pipe.get("fill_count") or 0) >= 1
        checks["kill_switch_works"] = pipe.get("kill_switch_active") is True
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline:{e}")
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")

    # Broker refusal
    checks["broker_refused"] = svc.refuse_broker().get("refused") is True
    checks["cred_refused"] = svc.refuse_credentials("x").get("refused") is True
    checks["real_order_refused"] = svc.refuse_real_order().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True
    checks["live_refused"] = svc.refuse_live().get("refused") is True

    # Session closed rejects market
    try:
        from saathi.platform.tg.paper_simulation.errors import PaperSimError
        svc.exchange.set_session("AAPL", "CLOSED")
        pf = svc.create_portfolio("cert_session_probe", initial_cash=10_000)
        try:
            svc.submit_order(pf["portfolio_id"], "AAPL", "BUY", "MARKET", 1)
            checks["closed_session_blocks"] = False
            failures.append("closed_session_allowed")
        except PaperSimError as e:
            checks["closed_session_blocks"] = e.code == "SESSION_NOT_OPEN"
        finally:
            svc.exchange.set_session("AAPL", "OPEN")
    except Exception as e:
        checks["closed_session_blocks"] = False
        failures.append(f"session:{e}")

    # Kill switch blocks orders
    try:
        from saathi.platform.tg.paper_simulation.errors import PaperSimError
        pf = svc.create_portfolio("cert_ks_probe", initial_cash=10_000)
        ks = svc.activate_kill_switch("cert probe", scope="PORTFOLIO", scope_ref=pf["portfolio_id"], actor="operator")
        try:
            svc.submit_order(pf["portfolio_id"], "SPY", "BUY", "MARKET", 1)
            checks["kill_switch_blocks"] = False
            failures.append("kill_switch_bypass")
        except PaperSimError as e:
            checks["kill_switch_blocks"] = e.code == "KILL_SWITCH_ACTIVE"
        svc.deactivate_kill_switch(ks["kill_switch_id"], actor="operator")
    except Exception as e:
        checks["kill_switch_blocks"] = False
        failures.append(f"ks:{e}")

    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security")

    ok = len(failures) == 0 and checks.get("pipeline_ok")
    verdict = TERMINAL_VERDICT if ok else "M288_M295_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "pipeline": {
            "portfolio_id": pipe.get("portfolio_id"),
            "fill_count": pipe.get("fill_count"),
        },
        "limitations": [
            "Virtual exchange only — not a real market venue",
            "Simulated liquidity, latency, and slippage models",
            "Margin is research-only with hard leverage caps",
            "No broker connectivity or real order routing",
            "Corporate action library is sample/demo scale",
        ],
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO ps_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    return result
