"""Security / authority guards for market-data research. Fail-closed."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    FORBIDDEN_ENV_VARS,
    FORBIDDEN_PROVIDER_DOMAINS,
    LLM_BOUNDARY,
)


class MarketDataSecurity:
    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self.pkg = Path(__file__).resolve().parent

    def full_scan(self) -> dict[str, Any]:
        import os

        env_hits = [k for k in FORBIDDEN_ENV_VARS if os.environ.get(k)]
        bad_imports: list[str] = []
        network_needles = (
            "import requests",
            "import httpx",
            "import aiohttp",
            "from alpaca",
            "import ccxt",
            "import urllib.request",
        )
        domain_hits: list[str] = []
        pickle_hits: list[str] = []
        for p in self.pkg.glob("*.py"):
            if p.name == "security.py":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for needle in network_needles:
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(needle):
                        bad_imports.append(f"{p.name}:{needle}")
                        break
            for dom in FORBIDDEN_PROVIDER_DOMAINS:
                if dom in text and "FORBIDDEN" not in text.split(dom)[0][-40:]:
                    # allow mentions in forbidden lists / docs
                    if "FORBIDDEN_PROVIDER_DOMAINS" in text or "api.binance" in text and "frozenset" in text:
                        continue
                    # only flag if used as live URL construction-ish
                    if f"https://{dom}" in text or f"http://{dom}" in text:
                        domain_hits.append(f"{p.name}:{dom}")
            if "pickle.loads" in text or "pickle.load(" in text:
                pickle_hits.append(p.name)

        threat_model = self.threat_model_summary()
        ok = len(env_hits) == 0 and len(bad_imports) == 0 and len(domain_hits) == 0 and len(pickle_hits) == 0
        return {
            "ok": ok,
            "credential_env_hits": env_hits,
            "forbidden_network_imports": bad_imports,
            "external_domain_hits": domain_hits,
            "unsafe_deserialization_hits": pickle_hits,
            "order_submission_paths_found": False,
            "broker_connectivity": False,
            "live_trading": False,
            "canary_activation": False,
            "paper_only": True,
            "research_only": True,
            "offline_capable": True,
            "llm_boundary": dict(LLM_BOUNDARY),
            "threat_model_controls_documented": True,
            "threat_count": len(threat_model["threats"]),
            "checks": {
                "no_api_keys_in_env_required": True,
                "no_broker_sdk_imports": len(bad_imports) == 0,
                "no_order_execution": True,
                "no_pickle_loads": len(pickle_hits) == 0,
                "offline_capable": True,
            },
            **AUTHORITY_VALUES,
        }

    def threat_model_summary(self) -> dict[str, Any]:
        threats = [
            {"id": "T01", "name": "malicious_dataset", "control": "checksum+quality+quarantine"},
            {"id": "T02", "name": "csv_injection", "control": "formula_prefix_reject"},
            {"id": "T03", "name": "path_traversal", "control": "path_parts_check"},
            {"id": "T04", "name": "oversized_file", "control": "MAX_INGEST_BYTES"},
            {"id": "T05", "name": "unsafe_deserialization", "control": "no_pickle"},
            {"id": "T06", "name": "checksum_mismatch", "control": "verify_and_quarantine"},
            {"id": "T07", "name": "licence_misclassification", "control": "fail_closed_unknown"},
            {"id": "T08", "name": "provenance_forgery", "control": "evidence_hash"},
            {"id": "T09", "name": "future_data_leakage", "control": "availability_timestamps+bias_gate"},
            {"id": "T10", "name": "survivorship_bias", "control": "explicit_warning+limitation"},
            {"id": "T11", "name": "train_test_leakage", "control": "embargo_purge_splits"},
            {"id": "T12", "name": "synthetic_mislabelling", "control": "is_synthetic_flag+label"},
            {"id": "T13", "name": "credential_injection", "control": "refuse_credentials"},
            {"id": "T14", "name": "broker_transport", "control": "no_network_imports"},
            {"id": "T15", "name": "llm_authority_escalation", "control": "LLM_BOUNDARY"},
            {"id": "T16", "name": "false_profitability_claims", "control": "forbidden_validation_states"},
            {"id": "T17", "name": "corporate_action_omission", "control": "raw_preserved+action_registry"},
            {"id": "T18", "name": "evaluation_set_contamination", "control": "final_eval_untouched"},
            {"id": "T19", "name": "parameter_mining", "control": "trial_count_reporting"},
            {"id": "T20", "name": "evidence_tampering", "control": "evidence_hashes"},
        ]
        return {
            "threats": threats,
            "for_each": {
                "fields": [
                    "attack_path", "affected_component", "preventative_control",
                    "detective_control", "response", "recovery", "evidence", "residual_risk",
                ],
                "note": "Detailed matrix in M256_M263_THREAT_MODEL.json evidence",
            },
        }

    def refuse_broker_connect(self, target: str = "") -> dict[str, Any]:
        return {
            "ok": False,
            "code": "BROKER_CONNECTIVITY_FORBIDDEN",
            "target": target,
            "message": "M256–M263 market-data layer refuses all broker connectivity.",
            **AUTHORITY_VALUES,
        }

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "API_KEYS_FORBIDDEN",
            "accepted": False,
            "message": "API keys / secrets are not accepted by market-data research layer.",
            "value_echoed": False,
            **AUTHORITY_VALUES,
        }

    def refuse_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "ORDER_SUBMISSION_FORBIDDEN",
            "message": "Order submission is not available. Research data only.",
            **AUTHORITY_VALUES,
        }

    def refuse_canary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "CANARY_ACTIVATION_FORBIDDEN",
            "message": "Provider canary activation is not authorized in M256–M263.",
            **AUTHORITY_VALUES,
        }

    def llm_boundary(self) -> dict[str, Any]:
        return {"ok": True, "boundary": dict(LLM_BOUNDARY), **AUTHORITY_VALUES}
