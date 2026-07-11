"""M15 connector health platform — per-connector health with honest labels.

Health never invents "connected" — a connector with no credential in this
environment reports its integration_status (e.g. environment-blocked), not a
green light. Local adapters that genuinely run report live health.
"""
from __future__ import annotations

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import credentials as C
from saathi.connectors.platform.models import _now_iso


def connector_health(connector_id: str) -> dict:
    conn = R.get_connector(connector_id)
    if conn is None:
        return {"connector_id": connector_id, "status": "unknown"}
    adapter = R.get_adapter(connector_id)
    ah = adapter.health() if adapter else {"status": "unavailable"}
    # honesty: cloud connectors with no secret present are not "healthy"
    has_cred = True
    if not conn.local and conn.required_credentials:
        has_cred = any(bool(__import__("os").getenv(k)) for k in conn.required_credentials)
    status = ah.get("status", "unknown")
    if not conn.local and not has_cred:
        status = conn.integration_status  # environment-blocked / contract-ready
    return {
        "connector_id": connector_id, "display_name": conn.display_name,
        "category": conn.category, "local": conn.local,
        "integration_status": conn.integration_status,
        "credential_present": has_cred, "adapter": ah,
        "status": status, "checked_at": _now_iso(),
    }


def platform_health() -> dict:
    conns = [connector_health(c.connector_id) for c in R.all_connectors()]
    by_status: dict = {}
    for c in conns:
        by_status[c["status"]] = by_status.get(c["status"], 0) + 1
    return {"connectors": conns, "summary": by_status,
            "total": len(conns), "checked_at": _now_iso()}
