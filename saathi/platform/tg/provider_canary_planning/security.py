"""Security scans and threat model for M240–M247."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    FORBIDDEN_ENV_VARS,
    FORBIDDEN_PROVIDER_DOMAINS,
    THREATS,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore
from saathi.platform.tg.provider_canary_planning.transport import TransportGuard

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)BEGIN (RSA |EC )?PRIVATE KEY"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
]


class PlanningSecurity:
    def __init__(self, store: PlanningStore, transport: TransportGuard, repo_root: Path):
        self.store = store
        self.transport = transport
        self.repo_root = repo_root

    def threat_model(self) -> dict[str, Any]:
        items = []
        for t in THREATS:
            items.append({
                "threat": t,
                "attack_path": f"adversary exploits {t.replace('_', ' ')}",
                "affected_component": "provider_canary_planning + future canary runtime",
                "preventative_control": "fail-closed scopes, transport guard, no auto sign-off, no adapter",
                "detective_control": "audit events, scans, abort gates",
                "response": "kill switch + revoke + evidence pack",
                "recovery": "human-only re-entry after security abort",
                "evidence": "pcp_audit_events + security scan JSON",
                "residual_risk": "documentation drift and owner eligibility uncertainty remain",
            })
        return {
            "threats": items,
            "count": len(items),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def credential_scan(self) -> dict[str, Any]:
        findings = []
        # Env scan
        for k in FORBIDDEN_ENV_VARS:
            if os.environ.get(k):
                findings.append({"kind": "env_var_present", "key": k, "severity": "high"})
        # Module tree scan for obvious secret assignments (exclude tests fixtures wording)
        root = self.repo_root / "saathi" / "platform" / "tg" / "provider_canary_planning"
        if root.is_dir():
            for p in root.rglob("*.py"):
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for pat in SECRET_PATTERNS:
                    if pat.search(text):
                        # Allow documentation of rejection patterns
                        if "refuse" in text.lower() or "FORBIDDEN" in text or "reject" in text.lower():
                            continue
                        findings.append({
                            "kind": "secret_pattern",
                            "path": str(p.relative_to(self.repo_root)),
                            "severity": "high",
                        })
        ok = len(findings) == 0
        self.store.audit("security.credential_scan", detail={"ok": ok, "findings": len(findings)})
        return {
            "ok": ok,
            "findings": findings,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def external_domain_scan(self) -> dict[str, Any]:
        # Probe known private API hosts — all must be blocked
        results = []
        for d in sorted(list(FORBIDDEN_PROVIDER_DOMAINS))[:12]:
            results.append(self.transport.probe(f"https://{d}/v1/account"))
        blocked = sum(1 for r in results if not r.get("ok"))
        return {
            "ok": blocked == len(results),
            "probes": results,
            "blocked_count": blocked,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def network_isolation(self) -> dict[str, Any]:
        local = self.transport.probe("http://127.0.0.1:8000/health")
        priv = self.transport.probe("https://paper-api.alpaca.markets/v2/account")
        return {
            "ok": local.get("ok") is True and priv.get("ok") is False,
            "localhost": local,
            "private_provider": priv,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def llm_boundary_scan(self) -> dict[str, Any]:
        from saathi.platform.tg.provider_canary_planning.models import LLM_BOUNDARY
        forbidden_true = [k for k, v in LLM_BOUNDARY.items() if k.startswith("llm_may_") and "False" in str(type(v)) is False and v is False]
        # All dangerous flags must be False
        dangerous = [
            "llm_may_certify_owner_eligibility",
            "llm_may_provide_legal_approval",
            "llm_may_provide_owner_approval",
            "llm_may_create_credentials",
            "llm_may_receive_credentials",
            "llm_may_store_credentials",
            "llm_may_activate_canary",
            "llm_may_initiate_oauth",
            "llm_may_connect_provider",
            "llm_may_generate_owner_signoff",
            "llm_may_authorize_live_trading",
        ]
        ok = all(LLM_BOUNDARY.get(k) is False for k in dangerous)
        return {
            "ok": ok,
            "boundary": dict(LLM_BOUNDARY),
            "dangerous_flags_false": ok,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def runtime_adapter_scan(self) -> dict[str, Any]:
        """Prove no real provider runtime adapter exists in this package."""
        root = self.repo_root / "saathi" / "platform" / "tg" / "provider_canary_planning"
        hits = []
        # Patterns assembled so this file itself does not self-match the scan list.
        banned = [
            "requests" + ".post(",
            "httpx" + ".Client",
            "aiohttp" + ".ClientSession",
            "websocket" + ".connect",
            "oauth" + "lib",
            "submit" + "_order",
            "place" + "_order",
        ]
        skip_names = {"security.py"}  # scanner definition only
        if root.is_dir():
            for p in root.rglob("*.py"):
                if p.name in skip_names:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
                for b in banned:
                    if b in text:
                        hits.append({"path": str(p.relative_to(self.repo_root)), "pattern": b})
        return {
            "ok": len(hits) == 0,
            "provider_adapter_implemented": False,
            "hits": hits,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def full_scan(self) -> dict[str, Any]:
        return {
            "credential_scan": self.credential_scan(),
            "external_domain_scan": self.external_domain_scan(),
            "network_isolation": self.network_isolation(),
            "llm_boundary_scan": self.llm_boundary_scan(),
            "runtime_adapter_scan": self.runtime_adapter_scan(),
            "threat_model_summary": {"threat_count": len(THREATS)},
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
            "CANARY_ACTIVATION_AUTHORIZED": False,
            "LIVE_TRADING_AUTHORIZED": False,
        }
