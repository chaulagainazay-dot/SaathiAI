"""Availability checks for role ``requires`` keys.

Each check returns ``(state, reason)`` with state in
``AVAILABLE | NOT_CONNECTED | UNAVAILABLE | UNKNOWN``. A check never pretends a
connector is live: no credential → NOT_CONNECTED; no integration → UNAVAILABLE;
exception while checking → UNKNOWN.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

AVAILABLE, NOT_CONNECTED, UNAVAILABLE, UNKNOWN = (
    "AVAILABLE", "NOT_CONNECTED", "UNAVAILABLE", "UNKNOWN")

# Providers SaathiOS has no integration for at all (declared honestly).
_NO_INTEGRATION = {
    "provider:onchain": "No on-chain data provider is integrated",
    "provider:social_sentiment": "No social-sentiment data provider is integrated",
    "provider:travel": "No travel provider is integrated",
}
_LIVE_CONNECTOR_STATES = {"healthy", "live-tested", "connected", "ok"}


def _connector(connector_id: str) -> tuple[str, str]:
    from saathi.connectors.platform.health import connector_health
    h = connector_health(connector_id)
    status = str(h.get("status", "unknown"))
    if status == "unknown":
        return UNKNOWN, f"Connector {connector_id} status unknown"
    if not h.get("credential_present", False) and not h.get("local", False):
        return NOT_CONNECTED, f"{h.get('display_name', connector_id)}: not connected ({status})"
    if status in _LIVE_CONNECTOR_STATES:
        return AVAILABLE, ""
    return NOT_CONNECTED, f"{h.get('display_name', connector_id)}: {status}"


def _platform_db() -> Path:
    import os
    env = os.environ.get("SAATHI_PLATFORM_DB")
    return Path(env) if env else ROOT / "data" / "platform" / "platform.db"


def _nepse_market_data() -> tuple[str, str]:
    p = _platform_db()
    if not p.exists():
        return UNAVAILABLE, "Market-data store not present"
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    try:
        n = c.execute("SELECT COUNT(*) FROM md_bars WHERE instrument LIKE 'NEPSE:%'").fetchone()[0]
    finally:
        c.close()
    return (AVAILABLE, "") if n else (UNAVAILABLE, "No NEPSE bars recorded in the market-data store")


def check(key: str) -> tuple[str, str]:
    try:
        if key in _NO_INTEGRATION:
            return UNAVAILABLE, _NO_INTEGRATION[key]
        if key.startswith("connector:"):
            return _connector(key.split(":", 1)[1])
        if key == "engine:nepse_market_data":
            return _nepse_market_data()
        return UNKNOWN, f"No availability check for {key}"
    except Exception as exc:  # never fabricate; degrade to UNKNOWN
        return UNKNOWN, f"Availability check failed for {key}: {type(exc).__name__}"


def check_all(keys) -> dict[str, tuple[str, str]]:
    return {k: check(k) for k in sorted(set(keys))}
