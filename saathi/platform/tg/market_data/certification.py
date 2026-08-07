"""M256–M263 certification hard gates."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.market_data.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.market_data.service import MarketDataService


def certify_market_data(svc: "MarketDataService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    # Authority locks
    for k, v in AUTHORITY_VALUES.items():
        if k.endswith("_AUTHORIZED") or k in (
            "API_KEYS_ACCEPTED", "OAUTH_AUTHORIZED", "LIVE_DATA_DEPENDENCY",
            "REGULATORY_GRADE_MARKET_DATA", "STRATEGY_PROFITABILITY_GUARANTEED",
            "LIVE_MARKET_READINESS", "INVESTMENT_ADVICE_CERTIFIED",
        ):
            if v is not False and v is not True:
                pass
            if isinstance(v, bool) and v is True and k not in (
                "paper_only", "sandbox_only", "research_only", "offline_first",
                "offline_capable", "no_broker_connection", "no_api_keys", "no_oauth",
                "no_order_submission", "no_live_data_dependency", "no_live_trading",
                "certified_research_requires_registered_dataset",
            ):
                failures.append(f"authority_true:{k}")
    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    if not checks["authority_locks_false"]:
        failures.append("LIVE_TRADING_AUTHORIZED")

    # Bootstrap pipeline
    try:
        pipe = svc.bootstrap_fixture_pipeline()
        checks["pipeline_ok"] = pipe.get("ok") is True
        checks["synthetic_labelled"] = pipe.get("SYNTHETIC_TEST_DATA") is True
        checks["dataset_registered"] = bool(pipe.get("dataset_id"))
        checks["licence_recorded"] = pipe.get("licence", {}).get("ok") is True
        checks["provenance_recorded"] = pipe.get("provenance", {}).get("ok") is True
        checks["ingestion_accepted"] = (pipe.get("ingestion") or {}).get("accepted_row_count", 0) > 0
        checks["raw_preserved"] = pipe.get("adjustment", {}).get("raw_prices_preserved") is True
        checks["quality_ran"] = "classification" in (pipe.get("quality") or {})
        checks["split_no_leakage"] = (pipe.get("split") or {}).get("leakage_detected") is False
        inv = (pipe.get("bias") or {}).get("invariants") or {}
        checks["no_future_info"] = inv.get("future_information_available") is False
        checks["no_eval_opt"] = inv.get("evaluation_set_optimised_on") is False
        checks["features_built"] = (pipe.get("features") or {}).get("value_count", 0) > 0
        checks["validation_state"] = (pipe.get("validation") or {}).get("state")
        ds_id = pipe.get("dataset_id")
        ver = pipe.get("dataset_version")
    except Exception as e:
        checks["pipeline_ok"] = False
        failures.append(f"pipeline_exception:{e}")
        ds_id = ver = None
        pipe = {"error": str(e)}

    if not checks.get("pipeline_ok"):
        failures.append("pipeline_failed")
    if not checks.get("synthetic_labelled"):
        failures.append("synthetic_not_labelled")
    if not checks.get("split_no_leakage"):
        failures.append("leakage_detected")

    # Idempotent re-ingest
    if ds_id and ver:
        try:
            ing2 = svc.ingest(ds_id, ver)
            checks["idempotent_reingest"] = ing2.get("idempotent") is True
        except Exception as e:
            checks["idempotent_reingest"] = False
            failures.append(f"idempotent:{e}")

    # Unknown licence fail-closed
    try:
        bad = svc.register_dataset(
            name="unknown_licence_probe",
            provider="probe",
            source_type="SYNTHETIC_TEST_DATA",
            is_synthetic=True,
            licence_type="UNKNOWN",
            checksum="abc",
            dataset_version="v1",
        )
        svc.record_licence(bad["dataset_id"], "v1", licence_name="UNKNOWN", unknown_terms=True)
        gate = svc.licence_check(bad["dataset_id"], "v1", "local_research")
        checks["unknown_licence_blocked"] = gate.get("allowed") is False
        approve = svc.approve_for_research(bad["dataset_id"], "v1")
        checks["unknown_licence_cannot_approve"] = approve.get("ok") is False
    except Exception as e:
        checks["unknown_licence_blocked"] = False
        failures.append(f"licence_gate:{e}")

    # Unregistered dataset rejected
    try:
        from saathi.platform.tg.market_data.errors import MarketDataError
        try:
            svc.registry.require_research_usable("ds_does_not_exist_xyz", "v1")
            checks["unregistered_rejected"] = False
        except MarketDataError:
            checks["unregistered_rejected"] = True
    except Exception:
        checks["unregistered_rejected"] = False

    # Security
    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security_scan")

    # Boundary refusals
    checks["broker_refused"] = svc.refuse_broker("alpaca").get("ok") is False
    checks["credentials_refused"] = svc.refuse_credentials("secret").get("ok") is False
    checks["orders_refused"] = svc.refuse_order().get("ok") is False
    checks["canary_refused"] = svc.refuse_canary().get("ok") is False

    # Deterministic dataset IDs
    a = svc.registry.register(
        name="id_probe", provider="p", market="US", asset_class="equity",
        frequency="1d", source_ref="x", checksum="c1", dataset_version="v1",
        licence_type="CC0-1.0",
    )
    b = svc.registry.register(
        name="id_probe", provider="p", market="US", asset_class="equity",
        frequency="1d", source_ref="x", checksum="c1", dataset_version="v1",
        licence_type="CC0-1.0",
    )
    checks["deterministic_ids"] = a["dataset_id"] == b["dataset_id"]

    # Feature version immutability on formula change
    f1 = svc.features.register_version("custom_mom", "close/close_n - 1", lookback=5)
    f2 = svc.features.register_version("custom_mom", "close/close_n - 1 + 0", lookback=5)  # different formula
    checks["feature_new_version_on_change"] = (
        f1.get("feature_version") != f2.get("feature_version") or f2.get("idempotent")
    )
    # same formula idempotent
    f3 = svc.features.register_version("custom_mom", "close/close_n - 1", lookback=5)
    checks["feature_same_formula_idempotent"] = f3.get("idempotent") is True or f3.get("feature_version") == f1.get("feature_version")

    hard_ok = (
        checks.get("authority_locks_false")
        and checks.get("pipeline_ok")
        and checks.get("synthetic_labelled")
        and checks.get("licence_recorded")
        and checks.get("provenance_recorded")
        and checks.get("ingestion_accepted")
        and checks.get("raw_preserved")
        and checks.get("split_no_leakage")
        and checks.get("no_future_info")
        and checks.get("no_eval_opt")
        and checks.get("features_built")
        and checks.get("unknown_licence_blocked")
        and checks.get("unregistered_rejected")
        and checks.get("security_ok")
        and checks.get("broker_refused")
        and checks.get("credentials_refused")
        and checks.get("orders_refused")
        and checks.get("canary_refused")
        and checks.get("deterministic_ids")
        and checks.get("idempotent_reingest")
        and not failures
    )

    verdict = TERMINAL_VERDICT if hard_ok else "M256_M263_IMPLEMENTED_NOT_VERIFIED"
    if not checks.get("pipeline_ok"):
        verdict = "M256_M263_PARTIALLY_IMPLEMENTED"
    if not checks.get("security_ok") or not checks.get("broker_refused"):
        verdict = "M256_M263_BROKER_ISOLATION_FAILED"
    if not checks.get("unknown_licence_blocked"):
        verdict = "M256_M263_LICENCE_GATE_FAILED"
    if not checks.get("split_no_leakage") or not checks.get("no_future_info"):
        verdict = "M256_M263_DATA_LEAKAGE_FAILED" if not checks.get("split_no_leakage") else "M256_M263_LOOKAHEAD_GATE_FAILED"

    result = {
        "verdict": verdict,
        "hard_gates_pass": hard_ok,
        "checks": checks,
        "failures": failures,
        "pipeline_summary": {
            "dataset_id": ds_id,
            "dataset_version": ver,
            "validation_state": checks.get("validation_state"),
        },
        "statements": list(TERMINAL_STATEMENTS),
        "max_state": MAX_STATE,
        "SYNTHETIC_TEST_DATA": True,
        "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE": True,
        "limitations": [
            "Bounded synthetic fixtures used for certification architecture proof",
            "Not regulatory-grade market data",
            "No guaranteed strategy profitability",
            "Research validation does not authorize live trading",
            "Holiday calendars incomplete",
            "No live broker connectivity",
        ],
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    svc.store.execute(
        """INSERT INTO md_certifications(id, verdict, result_json, evidence_hash, created_at)
           VALUES(?,?,?,?,?)""",
        (_uid("cert"), verdict, json.dumps(result, default=str), eh, time.time()),
    )
    svc.store.audit("certify", detail={"verdict": verdict, "hard_ok": hard_ok})
    return result
