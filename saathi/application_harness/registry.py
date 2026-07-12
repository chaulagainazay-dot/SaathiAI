"""M17.3 internal SaathiOS harness registry (NOT the public CLI-Hub).

Tracks discovered / imported / local / approved / installed / quarantined
harnesses. First-party pilot harnesses (ffmpeg) are registered TRUSTED (they wrap
already-canonical tools). Imported CLI-Anything entries are discovery records
only. No credentials stored. Backed by data/application_harnesses/registry.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from saathi.application_harness.models import HarnessDefinition, TrustStatus
from saathi.application_harness.pilots import ffmpeg as _ffmpeg

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "application_harnesses" / "registry.json"

_REG: dict[str, HarnessDefinition] = {}


def _bootstrap():
    if _REG:
        return
    # first-party pilots
    if _ffmpeg.available()["available"]:
        d = _ffmpeg.definition()
        _REG[d.harness_id] = d
    from saathi.application_harness.pilots import sqlite_harness as _sq
    if _sq.available()["available"]:
        d = _sq.definition()
        _REG[d.harness_id] = d
    from saathi.application_harness.pilots import jq_harness as _jq
    if _jq.available()["available"]:
        d = _jq.definition()
        _REG[d.harness_id] = d
    # additional pilot apps — present ones become approved, absent stay
    # discovered (dependency-blocked; cannot execute)
    from saathi.application_harness.pilots import apps as _apps
    for d in _apps.all_defs():
        _REG[d.harness_id] = d


def register(defn: HarnessDefinition) -> None:
    _REG[defn.harness_id] = defn


def get(harness_id: str) -> HarnessDefinition | None:
    _bootstrap()
    return _REG.get(harness_id)


def all_harnesses() -> list[HarnessDefinition]:
    _bootstrap()
    return list(_REG.values())


def executable_harnesses() -> list[HarnessDefinition]:
    return [d for d in all_harnesses() if d.executable()]


def summary() -> dict:
    _bootstrap()
    by = {}
    for d in _REG.values():
        by[d.trust_status] = by.get(d.trust_status, 0) + 1
    return {"total": len(_REG), "by_trust": by,
            "executable": len(executable_harnesses()),
            "harnesses": [{"harness_id": d.harness_id, "application": d.application_name,
                           "version": d.version, "trust": d.trust_status,
                           "source_type": d.source_type,
                           "operations": len(d.supported_operations)}
                          for d in _REG.values()]}


def import_records(records: list) -> dict:
    """Add imported CLI-Anything discovery records (untrusted; never executable)."""
    added = 0
    for r in records:
        hid = r.get("harness_id")
        if hid and hid not in _REG:
            d = HarnessDefinition(**{k: r[k] for k in r
                                     if k in HarnessDefinition.__dataclass_fields__})
            d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value  # force untrusted
            _REG[hid] = d
            added += 1
    return {"added": added, "total": len(_REG)}


def persist() -> str:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({"harnesses": [d.to_dict() for d in _REG.values()]},
                                indent=2, default=str))
    return str(STORE)
