"""M319 certification hard gates for connectivity governance."""
from __future__ import annotations

import json
import time
from typing import Any, TYPE_CHECKING

from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    MAX_STATE,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.connectivity_governance.storage import evidence_hash, _uid

if TYPE_CHECKING:
    from saathi.platform.tg.connectivity_governance.service import ConnectivityGovernanceService


def certify_connectivity_governance(svc: "ConnectivityGovernanceService") -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    # Authority locks
    for k, v in AUTHORITY_VALUES.items():
        if k.endswith("_AUTHORIZED") or k in (
            "API_KEYS_ACCEPTED", "PRODUCTION_AUTHORIZED", "AUTOMATED_INVESTMENT_AUTHORITY",
        ):
            if v is True:
                failures.append(f"authority_true:{k}")
    checks["authority_locks_false"] = AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
    checks["no_provider_connection"] = AUTHORITY_VALUES["REAL_CONNECTIVITY_AUTHORIZED"] is False
    checks["no_credentials"] = AUTHORITY_VALUES["CREDENTIAL_PROVISIONING_AUTHORIZED"] is False
    checks["no_orders"] = AUTHORITY_VALUES["ORDER_SUBMISSION_AUTHORIZED"] is False
    checks["no_canary"] = AUTHORITY_VALUES["CANARY_ACTIVATION_AUTHORIZED"] is False

    # Charter
    charter = svc.charter()
    checks["charter_ok"] = charter.get("finalized") is True and len(charter.get("principles") or []) >= 20
    if not checks["charter_ok"]:
        failures.append("charter")

    # Authority model proofs
    am = svc.authority_model()
    checks["no_implicit_expansion"] = am.get("no_implicit_expansion", {}).get("ok") is True
    checks["deny_overrides_allow"] = am.get("deny_overrides_allow", {}).get("deny_overrides_allow") is True
    checks["expiry_ok"] = am.get("expiry", {}).get("ok") is True
    checks["revocation_ok"] = am.get("revocation", {}).get("ok") is True
    checks["emergency_override_ok"] = am.get("emergency_override", {}).get("emergency_dominates") is True
    for k in ("no_implicit_expansion", "deny_overrides_allow", "expiry_ok", "revocation_ok", "emergency_override_ok"):
        if not checks.get(k):
            failures.append(k)

    # Providers
    prov = svc.list_providers()
    checks["providers_ok"] = (prov.get("count") or 0) >= 1 and prov.get("any_connected") is False
    checks["no_active_provider"] = prov.get("any_active") is False
    if not checks["providers_ok"]:
        failures.append("providers")

    # Approval framework controls
    appr = svc.approval_framework_export()
    controls = appr.get("controls") or {}
    checks["maker_checker"] = controls.get("maker_checker") is True
    checks["no_self_approval_policy"] = controls.get("no_self_approval") is True
    checks["no_llm_approval_policy"] = controls.get("no_llm_approval") is True
    checks["approval_not_activation"] = controls.get("approval_does_not_equal_activation") is True

    # Live tests for self-approval and LLM
    try:
        draft = svc.create_approval(
            requestor="alice",
            approval_type="provider_documentation_review",
            provider="prov_mock_contract",
            environment="governance",
            capability_scope=["offline_fixture_access"],
            operation_scope=["documentation_review"],
            jurisdiction="N/A",
            expiry_time=time.time() + 86400,
            allowed_network_destinations=["localhost"],
            evidence_requirements=["docs_hash"],
            revocation_conditions=["operator_request"],
            acknowledgements=["governance_only", "no_activation"],
        )
        aid = draft["approval"]["approval_id"]
        svc.submit_approval(aid, actor="alice")
        try:
            svc.review_approval(aid, approver="alice", decision="approve")
            checks["self_approval_rejected"] = False
            failures.append("self_approval_allowed")
        except Exception:
            checks["self_approval_rejected"] = True
        try:
            svc.review_approval(aid, approver="llm", decision="approve")
            checks["llm_approval_rejected"] = False
            failures.append("llm_approval_allowed")
        except Exception:
            checks["llm_approval_rejected"] = True
        # proper approve still not active
        r = svc.review_approval(aid, approver="bob", decision="approve")
        checks["approved_not_active"] = (
            r["approval"]["status"] == "APPROVED_NOT_ACTIVE"
            and r.get("activates_connectivity") is False
        )
        if not checks["approved_not_active"]:
            failures.append("approval_activated")
    except Exception as e:
        checks["approval_flow_ok"] = False
        failures.append(f"approval_flow:{e}")
    else:
        checks["approval_flow_ok"] = True

    # Credential policy
    pol = svc.credential_policy()
    checks["raw_credentials_forbidden"] = pol.get("raw_credentials_forbidden") is True
    try:
        svc.reject_raw_credential("api_key", "sk_test_xxx")
        checks["raw_cred_rejected"] = True
    except Exception:
        checks["raw_cred_rejected"] = False
        failures.append("raw_cred")

    try:
        svc.scan_secrets({"api_key": "secret12345"})
        checks["secret_scan_blocks"] = False
        failures.append("secret_scan_allowed")
    except Exception:
        checks["secret_scan_blocks"] = True

    # Emergency
    em = svc.emergency_shutdown(actor="operator", reason="certification_drill")
    checks["emergency_ok"] = em.get("emergency_shutdown") is True
    bypass = svc.emergency_bypass_attempt()
    checks["emergency_no_bypass"] = bypass.get("refused") is True
    if not checks["emergency_no_bypass"]:
        failures.append("emergency_bypass")

    # Threats
    risks = svc.risk_summary()
    checks["threats_present"] = (risks.get("total_threats") or 0) >= 30
    checks["no_unresolved_critical"] = (risks.get("unresolved_critical") or []) == [] or len(risks.get("unresolved_critical") or []) == 0
    if not checks["threats_present"]:
        failures.append("threats")
    if risks.get("unresolved_critical"):
        failures.append("unresolved_critical")
        checks["no_unresolved_critical"] = False
    else:
        checks["no_unresolved_critical"] = True

    # Maturity
    mat = svc.maturity()
    checks["maturity_governance_only"] = mat.get("current") == CURRENT_MATURITY
    if not checks["maturity_governance_only"]:
        failures.append("maturity")

    # Security scan
    sec = svc.security_scan()
    checks["security_ok"] = sec.get("ok") is True
    if not checks["security_ok"]:
        failures.append("security")

    # Schema scan
    schema = svc.store.schema_scan()
    checks["schema_ok"] = schema.get("ok") is True
    if not checks["schema_ok"]:
        failures.append("schema")

    # Hard refusals
    checks["broker_refused"] = svc.refuse_broker_login().get("refused") is True
    checks["oauth_refused"] = svc.refuse_oauth().get("refused") is True
    checks["order_refused"] = svc.refuse_order().get("refused") is True
    checks["account_refused"] = svc.refuse_account_access().get("refused") is True
    checks["canary_refused"] = svc.refuse_canary().get("refused") is True
    checks["live_refused"] = svc.refuse_live_trading().get("refused") is True
    checks["connect_refused"] = svc.refuse_provider_connect().get("refused") is True
    for k in ("broker_refused", "oauth_refused", "order_refused", "account_refused", "canary_refused", "live_refused", "connect_refused"):
        if not checks.get(k):
            failures.append(k)

    ok = len(failures) == 0
    verdict = TERMINAL_VERDICT if ok else "M312_M319_PARTIALLY_IMPLEMENTED"
    result = {
        "ok": ok,
        "verdict": verdict,
        "max_state": MAX_STATE,
        "current_maturity": CURRENT_MATURITY,
        "browser_cert_verdict_target": BROWSER_CERT_VERDICT,
        "statements": list(TERMINAL_STATEMENTS),
        "checks": checks,
        "failures": failures,
        "limitations": [
            "Governance only — no provider connection",
            "No real credentials or OAuth",
            "No account, balance, or position access",
            "No order submission or canary activation",
            "Approvals never activate connectivity in this milestone",
            "Live trading remains prohibited",
        ],
        "purpose": "connectivity_governance_only",
        **AUTHORITY_VALUES,
    }
    eh = evidence_hash(result)
    result["evidence_hash"] = eh
    cid = _uid("cert")
    svc.store.execute(
        "INSERT INTO cg_certifications(id, verdict, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
        (cid, verdict, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
    )
    result["certification_id"] = cid
    svc.store.audit("certify", "system", cid, {"verdict": verdict, "ok": ok})
    return result
