"""M17.3 internal SaathiOS harness registry (NOT the public CLI-Hub).

Tracks discovered / imported / local / approved / installed / quarantined
harnesses. First-party pilot harnesses (ffmpeg) are registered TRUSTED (they wrap
already-canonical tools). Imported CLI-Anything entries are discovery records
only. No credentials stored. Backed by data/application_harnesses/registry.json.

M17.18: STORE is loaded on first bootstrap (fail-closed) and written on every
mutation so install/import/trust state survives process restart. No second
registry system.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from saathi.application_harness.models import (
    EXECUTABLE_TRUST,
    HarnessDefinition,
    TrustStatus,
)
from saathi.application_harness.pilots import ffmpeg as _ffmpeg

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "application_harnesses" / "registry.json"

_REG: dict[str, HarnessDefinition] = {}
_LAST_LOAD: dict = {"status": "not_attempted", "loaded": 0, "merged": 0,
                    "skipped": 0, "errors": []}

_MAX_STORE_BYTES = 5_000_000
_SECRET_KEY = re.compile(
    r"(password|secret|token|api[_-]?key|cookie|private[_-]?key|credential|"
    r"authorization|bearer|ssh[_-]?key)",
    re.I,
)
_SHELL_CHAIN = re.compile(r"[;&|`]|\$\(|\|\||&&|>|<")
_TRAVERSAL = re.compile(r"\.\.[\\/]")
# trust values that may be restored from disk onto an in-memory pilot (never elevate)
_RESTRICTIVE_TRUST = {
    TrustStatus.REJECTED.value,
    TrustStatus.QUARANTINED.value,
    TrustStatus.REVOKED.value,
    TrustStatus.COMPROMISED.value,
    TrustStatus.DEPRECATED.value,
    TrustStatus.INCOMPATIBLE.value,
    TrustStatus.EXTERNAL_UNTRUSTED.value,
}
_FIELD_NAMES = set(HarnessDefinition.__dataclass_fields__)


def _bootstrap():
    if _REG:
        return
    _seed_pilots()
    _load_store()


def _seed_pilots():
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
    from saathi.application_harness.pilots import zip_archive as _zip
    if _zip.available()["available"]:
        d = _zip.definition()
        _REG[d.harness_id] = d
    # additional pilot apps — present ones become approved, absent stay
    # discovered (dependency-blocked; cannot execute)
    from saathi.application_harness.pilots import apps as _apps
    for d in _apps.all_defs():
        _REG[d.harness_id] = d


def _scan_unsafe(obj) -> str | None:
    """Return a rejection code if the payload looks like secrets or shell."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _SECRET_KEY.search(str(k)):
                return "SECRET_KEY_REJECTED"
            code = _scan_unsafe(v)
            if code:
                return code
    elif isinstance(obj, list):
        for v in obj:
            code = _scan_unsafe(v)
            if code:
                return code
    elif isinstance(obj, str):
        if _SHELL_CHAIN.search(obj):
            return "EMBEDDED_SHELL_CHAIN"
        if _TRAVERSAL.search(obj):
            return "PATH_TRAVERSAL"
    return None


def _definition_from_record(r: dict) -> HarnessDefinition:
    if not isinstance(r, dict):
        raise ValueError("ENTRY_NOT_OBJECT")
    unsafe = _scan_unsafe(r)
    if unsafe:
        raise ValueError(unsafe)
    hid = str(r.get("harness_id", "")).strip()
    if not hid or len(hid) > 80:
        raise ValueError("BAD_HARNESS_ID")
    kwargs = {k: r[k] for k in r if k in _FIELD_NAMES}
    # never accept nested free-form secret bags
    kwargs.pop("required_environment_variables", None)
    d = HarnessDefinition(**kwargs)
    try:
        ts = TrustStatus(d.trust_status)
    except ValueError:
        d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value
        d.validation_status = "restored_invalid_trust"
        return d
    # non-pilot restores never auto-execute; force down if elevated on disk
    if ts in EXECUTABLE_TRUST and d.source_type in (
            "cli_anything", "source_checkout"):
        d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value
        d.validation_status = "restored_untrusted"
    return d


def _apply_restrictive_overlay(live: HarnessDefinition, disk: HarnessDefinition) -> bool:
    """Apply only more-restrictive trust from disk onto a code-seeded pilot.

    Returns True if live was mutated.
    """
    changed = False
    if disk.trust_status in _RESTRICTIVE_TRUST and live.trust_status != disk.trust_status:
        live.trust_status = disk.trust_status
        changed = True
    # restore validation marker when present and non-empty
    if disk.validation_status and disk.validation_status != live.validation_status:
        if disk.trust_status in _RESTRICTIVE_TRUST:
            live.validation_status = disk.validation_status
            changed = True
    if changed:
        live.updated_at = time.time()
    return changed


def _load_store() -> dict:
    """Load STORE into _REG. Fail-closed: corrupt/oversized file is ignored."""
    global _LAST_LOAD
    report = {"status": "missing", "loaded": 0, "merged": 0, "skipped": 0,
              "errors": [], "path": str(STORE)}
    if not STORE.exists():
        _LAST_LOAD = report
        return report
    try:
        raw = STORE.read_bytes()
        if len(raw) > _MAX_STORE_BYTES:
            report["status"] = "too_large"
            report["errors"].append("REGISTRY_TOO_LARGE")
            _LAST_LOAD = report
            return report
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        report["status"] = "invalid"
        report["errors"].append(f"REGISTRY_INVALID:{type(e).__name__}")
        _LAST_LOAD = report
        return report
    if not isinstance(doc, dict) or not isinstance(doc.get("harnesses"), list):
        report["status"] = "invalid_schema"
        report["errors"].append("REGISTRY_INVALID_SCHEMA")
        _LAST_LOAD = report
        return report
    for r in doc["harnesses"]:
        try:
            d = _definition_from_record(r)
        except Exception as e:
            report["skipped"] += 1
            report["errors"].append(str(getattr(e, "args", [e])[0]))
            continue
        if d.harness_id in _REG:
            if _apply_restrictive_overlay(_REG[d.harness_id], d):
                report["merged"] += 1
            else:
                report["skipped"] += 1
            continue
        # additional safety: non-pilot executable trust only for pure local system
        if TrustStatus(d.trust_status) in EXECUTABLE_TRUST:
            if d.source_type != "local" or d.install_method not in (
                    "system_executable", "bundled"):
                d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value
                d.validation_status = "restored_untrusted"
        _REG[d.harness_id] = d
        report["loaded"] += 1
    report["status"] = "ok"
    _LAST_LOAD = report
    return report


def load_report() -> dict:
    """Last boot-load report (diagnostics / Control Center)."""
    _bootstrap()
    return dict(_LAST_LOAD)


def register(defn: HarnessDefinition) -> None:
    _bootstrap()
    _REG[defn.harness_id] = defn
    persist()


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
            "store": str(STORE),
            "load": dict(_LAST_LOAD),
            "harnesses": [{"harness_id": d.harness_id, "application": d.application_name,
                           "version": d.version, "trust": d.trust_status,
                           "source_type": d.source_type,
                           "operations": len(d.supported_operations)}
                          for d in _REG.values()]}


def import_records(records: list) -> dict:
    """Add imported CLI-Anything discovery records (untrusted; never executable)."""
    _bootstrap()
    added = 0
    for r in records:
        hid = r.get("harness_id")
        if hid and hid not in _REG:
            d = HarnessDefinition(**{k: r[k] for k in r
                                     if k in HarnessDefinition.__dataclass_fields__})
            d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value  # force untrusted
            _REG[hid] = d
            added += 1
    if added:
        persist()
    return {"added": added, "total": len(_REG)}


def persist() -> str:
    """Write current registry to STORE. Never writes secrets (definitions only)."""
    # ensure pilots are seeded if caller registered before first get()
    if not _REG:
        _seed_pilots()
    STORE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1,
               "harnesses": [d.to_dict() for d in _REG.values()]}
    text = json.dumps(payload, indent=2, default=str)
    # refuse to persist if somehow secrets snuck in
    if _scan_unsafe(payload):
        raise RuntimeError("REGISTRY_REFUSES_SECRET_PAYLOAD")
    STORE.write_text(text, encoding="utf-8")
    return str(STORE)


def reset_for_tests(*, store: Path | None = None) -> None:
    """Clear in-memory registry (and optionally retarget STORE). Tests only."""
    global STORE, _LAST_LOAD
    _REG.clear()
    _LAST_LOAD = {"status": "not_attempted", "loaded": 0, "merged": 0,
                  "skipped": 0, "errors": []}
    if store is not None:
        STORE = Path(store)
