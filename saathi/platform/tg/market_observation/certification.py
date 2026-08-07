"""M304–M311 certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.market_observation.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.market_observation.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.market_observation.service import MarketObservationService


def certify_market_observation(svc: "MarketObservationService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    for k in (
        "LIVE_TRADING_AUTHORIZED", "BROKER_CONNECTIVITY_AUTHORIZED",
        "ORDER_EXECUTION_AUTHORIZED", "ACCOUNT_ACCESS_AUTHORIZED",
        "CREDENTIAL_STORAGE_AUTHORIZED", "OAUTH_AUTHORIZED", "API_KEYS_ACCEPTED",
    ):
        if AUTHORITY_VALUES.get(k) is True:
            failures.append(f"authority_true:{k}")
    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    checks["no_credential_storage"] = AUTHORITY_VALUES["CREDENTIAL_STORAGE_AUTHORIZED"] is False
    checks["no_account_access"] = AUTHORITY_VALUES["ACCOUNT_ACCESS_AUTHORIZED"] is False

    try:
        pipe = svc.bootstrap_demo_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["snapshot_ok"] = bool(pipe.get("snapshot_id"))
        checks["quotes_ok"] = (pipe.get("quote_count") or 0) >= 1
        checks["symbols_ok"] = (pipe.get("symbol_count") or 0) >= 1
        checks["history_ok"] = (pipe.get("history_bars") or 0) >= 1
        checks["exchange_status_ok"] = (pipe.get("exchange_count") or 0) >= 1
        checks["corporate_actions_ok"] = pipe.get("corporate_actions_ok") is True
        checks["benchmarks_ok"] = (pipe.get("benchmark_count") or 0) >= 1
        checks["offline_source"] = pipe.get("authenticated_live") is False
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline:{e}")
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")
    if not checks.get("offline_source"):
        failures.append("authenticated_live_present")

    # Hard refusals
    checks["broker_login_refused"] = svc.refuse_broker_login().get("refused") is True
    checks["oauth_refused"] = svc.refuse_oauth().get("refused") is True
    checks["credentials_refused"] = svc.refuse_credentials("x").get("refused") is True
    checks["orders_refused"] = svc.refuse_order().get("refused") is True
    checks["account_refused"] = svc.refuse_account_access().get("refused") is True
    checks["portfolio_refused"] = svc.refuse_portfolio_access().get("refused") is True
    checks["balance_refused"] = svc.refuse_balance_access().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True
    checks["live_refused"] = svc.refuse_live_trading().get("refused") is True
    checks["auth_feed_refused"] = svc.refuse_authenticated_live_feed().get("refused") is True

    for k in (
        "broker_login_refused", "oauth_refused", "credentials_refused", "orders_refused",
        "account_refused", "portfolio_refused", "balance_refused", "live_refused",
    ):
        if not checks.get(k):
            failures.append(k)

    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security")

    # Schema must not store credentials
    try:
        svc.store.execute("SELECT 1")  # ok
        try:
            svc.store.execute("INSERT INTO mo_meta(key, value, updated_at) VALUES('api_key','x',0)")
            checks["credential_sql_blocked"] = False
            failures.append("credential_sql_allowed")
        except ValueError:
            checks["credential_sql_blocked"] = True
    except Exception as e:
        checks["credential_sql_blocked"] = False
        failures.append(f"sql:{e}")

    ok = len(failures) == 0 and checks.get("pipeline_ok")
    verdict = TERMINAL_VERDICT if ok else "M304_M311_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "pipeline": {
            "snapshot_id": pipe.get("snapshot_id"),
            "quote_count": pipe.get("quote_count"),
        },
        "limitations": [
            "Offline fixtures / frozen local observation only",
            "Not a live authenticated market data feed",
            "Validation purpose — not trading",
            "No broker, account, balance, or portfolio access",
            "No credential storage",
        ],
        "purpose": "validation_not_trading",
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO mo_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    return result
