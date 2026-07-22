"""M27 — Browser adapter: reuse saathi.browser governance; no second browser."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saathi.connectors.gov.models import ConnectorRequest, ConnectorResult
from saathi.connectors.gov.redaction import redact_payload


@dataclass
class BrowserAdapter:
    name: str = "browser"

    def execute(self, request: ConnectorRequest, **_: Any) -> ConnectorResult:
        op = request.operation
        url = str((request.payload or {}).get("url") or request.url or "")

        # Domain policy reuse
        domain_ok = True
        domain_detail = "no_url"
        if url:
            try:
                from saathi.browser.domain_policy import evaluate_url

                decision = evaluate_url(url)
                # Support dict or object
                if isinstance(decision, dict):
                    domain_ok = bool(decision.get("allowed", decision.get("ok", False)))
                    domain_detail = str(decision.get("reason") or decision.get("detail") or "")
                else:
                    domain_ok = bool(getattr(decision, "allowed", getattr(decision, "ok", False)))
                    domain_detail = str(getattr(decision, "reason", getattr(decision, "detail", "")))
            except Exception:
                # Fail closed if policy missing for navigate
                if op in ("navigate", "open", "fetch"):
                    domain_ok = False
                    domain_detail = "domain_policy_unavailable"
                else:
                    domain_ok = True
                    domain_detail = "policy_probe_skipped"

        if op in ("health", "validate", "policy_check"):
            return ConnectorResult(
                ok=True,
                connector_id=request.connector_id,
                operation=op,
                status="success",
                detail="browser_governance_present",
                data=redact_payload({"domain_ok": domain_ok, "detail": domain_detail, "has_url": bool(url)}),
                privacy_safe=True,
                bypass=False,
            )

        if op in ("navigate", "open", "fetch"):
            if not url:
                return ConnectorResult(
                    ok=False,
                    connector_id=request.connector_id,
                    operation=op,
                    status="error",
                    detail="url_required",
                    bypass=False,
                )
            if not domain_ok:
                return ConnectorResult(
                    ok=False,
                    connector_id=request.connector_id,
                    operation=op,
                    status="denied",
                    detail=f"domain_policy:{domain_detail}",
                    bypass=False,
                )
            # M27 does not launch a live browser — governed dry result only
            return ConnectorResult(
                ok=True,
                connector_id=request.connector_id,
                operation=op,
                status="success",
                detail="browser_policy_passed_dry_run",
                data=redact_payload({
                    "url_host_only": _host(url),
                    "live_browser_launched": False,
                    "reused_module": "saathi.browser",
                }),
                privacy_safe=True,
                bypass=False,
            )

        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=op,
            status="denied",
            detail=f"browser_operation_not_enabled_m27:{op}",
            bypass=False,
        )


def _host(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "")[:200]
