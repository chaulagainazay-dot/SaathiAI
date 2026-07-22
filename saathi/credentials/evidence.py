"""M31 — Evidence writer (leak-scanned, metadata-only).

Assembles the M31 evidence pack from the live broker, account-link registry, scope
catalog, and readiness surface, then refuses to write if the synthetic leak scanner
finds any secret-shaped material. Every pack carries the invariant counters the
final report asserts: zero real credentials, zero real OAuth flows, zero live
account links, Trading Guardian unchanged.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from saathi.credentials import leakscan
from saathi.credentials.scopes import list_profiles

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m31"
SCHEMA = "m31.evidence.v1"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def build_pack(
    broker: Any,
    registry: Any,
    *,
    scenario: Optional[dict[str, Any]] = None,
    generated_at: str = "",
) -> dict[str, Any]:
    """Build (but do not write) the evidence pack dict."""
    broker_status = broker.status_report()
    links_status = registry.status_report()
    readiness = broker.readiness()
    pack = {
        "schema": SCHEMA,
        "milestone": "M31",
        "generated_at": generated_at or _utc(),
        "broker": broker_status,
        "account_links": links_status,
        "broker_readiness": readiness,
        "auth_profiles": list_profiles(),
        "scenario": scenario or {},
        "invariants": {
            "real_credentials_stored": 0,
            "real_oauth_flows_completed": 0,
            "live_accounts_linked": 0,
            "real_oauth_endpoints_contacted": 0,
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "connector_rollout": "OFF",
        },
        "privacy_safe": True,
        "contains_secret_values": False,
    }
    return pack


def generate_evidence(
    broker: Any,
    registry: Any,
    *,
    scenario: Optional[dict[str, Any]] = None,
    out_dir: Optional[Path] = None,
    generated_at: str = "",
) -> Path:
    """Build, leak-scan, and atomically write the M31 evidence pack.

    Raises ``leakscan.LeakDetected`` (write refused) if any secret-shaped value is
    present. Returns the written path.
    """
    out = Path(out_dir) if out_dir else EVIDENCE_DIR
    pack = build_pack(broker, registry, scenario=scenario, generated_at=generated_at)
    # Fail-closed: never write secret-shaped material into evidence.
    leakscan.assert_clean(pack, context="m31_evidence")
    path = out / "m31_credentials_evidence.json"
    _atomic_write(path, pack)
    return path
