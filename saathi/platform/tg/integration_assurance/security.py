"""Security scanners for M232–M239 integration assurance."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import (
    FORBIDDEN_ENV_VARS,
    FORBIDDEN_PROVIDER_DOMAINS,
    REAL_CONNECTIVITY_AUTHORIZED,
)
from saathi.platform.tg.integration_assurance.store import AssuranceStore, _uid


class AssuranceSecurity:
    def __init__(self, store: AssuranceStore, transport: Any, repo_root: Path | None = None):
        self.store = store
        self.transport = transport
        self.root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]

    def _record(self, name: str, result: str, detail: dict) -> dict[str, Any]:
        self.store.execute(
            """INSERT INTO ia_security_checks(id, check_name, result, detail_json, created_at)
               VALUES(?,?,?,?,?)""",
            (_uid("sec"), name, result, json.dumps(detail), time.time()),
        )
        return {"check": name, "result": result, **detail}

    def credential_scan(self) -> dict[str, Any]:
        present = [k for k in FORBIDDEN_ENV_VARS if os.environ.get(k)]
        ok = len(present) == 0
        return self._record(
            "credential_scan",
            "PASS" if ok else "FAIL",
            {"forbidden_present": present, "ok": ok},
        )

    def external_domain_scan(self) -> dict[str, Any]:
        # Probe known broker domains — all must be blocked
        blocked = []
        for d in sorted(FORBIDDEN_PROVIDER_DOMAINS)[:12]:
            r = self.transport.probe(f"https://{d}/")
            blocked.append(r)
        all_blocked = all(b.get("blocked") for b in blocked)
        return self._record(
            "external_domain_scan",
            "PASS" if all_blocked else "FAIL",
            {"probes": blocked, "ok": all_blocked},
        )

    def llm_authority_scan(self) -> dict[str, Any]:
        # Structural: owner signoff automated flag must be false
        from saathi.platform.tg.integration_assurance.models import (
            LLM_BOUNDARY,
            OWNER_SIGNOFF_AUTOMATED,
        )
        ok = (
            OWNER_SIGNOFF_AUTOMATED is False
            and REAL_CONNECTIVITY_AUTHORIZED is False
            and LLM_BOUNDARY.get("llm_may_provide_owner_signoff") is False
            and LLM_BOUNDARY.get("llm_may_authorize_live_trading") is False
        )
        return self._record(
            "llm_authority_scan",
            "PASS" if ok else "FAIL",
            {
                "owner_signoff_automated": OWNER_SIGNOFF_AUTOMATED,
                "real_connectivity_authorized": REAL_CONNECTIVITY_AUTHORIZED,
                "ok": ok,
            },
        )

    def network_isolation(self) -> dict[str, Any]:
        probes = [
            self.transport.probe("https://api.binance.com/api/v3/account"),
            self.transport.probe("https://api.alpaca.markets/v2/account"),
            self.transport.probe("https://api.kite.trade/user/profile"),
            self.transport.probe("http://127.0.0.1:8839/health"),
            self.transport.probe("https://pypi.org/simple/fastapi/"),
        ]
        provider_blocked = all(
            p.get("blocked") for p in probes[:3]
        )
        local_ok = probes[3].get("ok") is True
        registry_ok = probes[4].get("ok") is True and probes[4].get("broker_connectivity") is False
        ok = provider_blocked and local_ok and registry_ok
        return self._record(
            "network_isolation",
            "PASS" if ok else "FAIL",
            {
                "probes": probes,
                "provider_blocked": provider_blocked,
                "localhost_allowed": local_ok,
                "registry_separated": registry_ok,
                "ok": ok,
            },
        )

    def secret_pattern_scan(self) -> dict[str, Any]:
        """Scan IA package for accidental hard-coded secrets (heuristic).

        Ignores this scanner's own pattern definitions and obvious test/docs strings.
        """
        ia = self.root / "saathi/platform/tg/integration_assurance"
        hits = []
        # Concrete secret material only (not regex source strings).
        patterns = [
            re.compile(r"sk-live-[A-Za-z0-9]{20,}"),
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"-----BEGIN RSA PRIVATE KEY-----\n[A-Za-z0-9+/=\n]{100,}"),
        ]
        if ia.is_dir():
            for py in ia.glob("*.py"):
                if py.name == "security.py":
                    continue  # scanner definitions only
                text = py.read_text(encoding="utf-8", errors="replace")
                for pat in patterns:
                    if pat.search(text):
                        hits.append(str(py.relative_to(self.root)))
                        break
        ok = len(hits) == 0
        return self._record("secret_pattern_scan", "PASS" if ok else "FAIL", {"hits": hits, "ok": ok})

    def run_all(self) -> dict[str, Any]:
        checks = [
            self.credential_scan(),
            self.external_domain_scan(),
            self.llm_authority_scan(),
            self.network_isolation(),
            self.secret_pattern_scan(),
        ]
        all_pass = all(c.get("result") == "PASS" for c in checks)
        return {
            "all_pass": all_pass,
            "checks": checks,
            "passed": sum(1 for c in checks if c.get("result") == "PASS"),
            "failed": sum(1 for c in checks if c.get("result") != "PASS"),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
