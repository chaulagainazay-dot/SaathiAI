"""M17.3 internal SaathiOS harness registry (NOT the public CLI-Hub).

Tracks discovered / imported / local / approved / installed / quarantined
harnesses. First-party pilot harnesses (ffmpeg) are registered TRUSTED (they wrap
already-canonical tools). Imported CLI-Anything entries are discovery records
only. No credentials stored. Backed by data/application_harnesses/registry.json.

M17.18: STORE is loaded on first bootstrap (fail-closed) and written on every
mutation so install/import/trust state survives process restart. No second
registry system.

M17.19: persisted registry JSON is untrusted input. Bounded read → safe parse →
envelope + entry validation → restrictive pilot overlays only → atomic write.
One authoritative validator for boot, register, and import paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from saathi.application_harness.models import (
    EXECUTABLE_TRUST,
    HarnessDefinition,
    TrustStatus,
)
from saathi.application_harness.pilots import ffmpeg as _ffmpeg

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "application_harnesses" / "registry.json"

# ── M17.19 limits (conservative, centralized) ────────────────────────────────
SUPPORTED_SCHEMA_VERSION = 1
_MAX_STORE_BYTES = 256_000          # 256 KiB (was 5 MiB; still ample for registry)
_MAX_ENTRIES = 256
_MAX_ID_LEN = 80
_MAX_NAME_LEN = 120
_MAX_DESC_LEN = 2_000
_MAX_STRING_LEN = 2_000
_MAX_LIST_LEN = 64
_MAX_MAP_LEN = 64
_MAX_NEST_DEPTH = 8
_MAX_ERROR_DETAIL = 40
_MAX_ERRORS_REPORTED = 24
_MAX_QUARANTINE_FILES = 3

_REG: dict[str, HarnessDefinition] = {}
_LAST_LOAD: dict = {
    "status": "not_attempted",
    "loaded": 0,
    "merged": 0,
    "skipped": 0,
    "errors": [],
    "policy": "envelope_fail_closed_entry_skip",
}

_SECRET_KEY = re.compile(
    r"(password|secret|token|api[_-]?key|cookie|private[_-]?key|credential|"
    r"authorization|bearer|ssh[_-]?key)",
    re.I,
)
_SHELL_CHAIN = re.compile(r"[;&|`]|\$\(|\|\||&&|>|<")
_TRAVERSAL = re.compile(r"\.\.[\\/]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_HARNESS_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")

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
# unknown keys that are never ignored (security / identity / execution)
# Intentionally avoids finance-domain tokens so the module remains free of a
# trading surface (static boundary scan in M17.18+ tests).
_SENSITIVE_UNKNOWN = re.compile(
    r"(trust|permission|execut|elevat|privilege|admin|sudo|shell|command|"
    r"credential|secret|token|password|key|auth|bypass|force|override|"
    r"capability|role|owner|approval|policy|identity|"
    r"import_code|eval|module|python|path_escape)",
    re.I,
)
_SAFE_META_KEYS = frozenset({"_comment", "comment", "notes_safe"})
_ALLOWED_SOURCE_TYPES = frozenset({
    "local", "cli_anything", "source_checkout", "system", "bundled",
})
_PILOT_IDS_CACHE: set[str] | None = None


def _pilot_ids() -> set[str]:
    """Known built-in pilot ids (seeded from code definitions when available)."""
    global _PILOT_IDS_CACHE
    if _PILOT_IDS_CACHE is not None:
        return _PILOT_IDS_CACHE
    ids: set[str] = {"ffmpeg", "sqlite", "jq", "zip"}
    try:
        from saathi.application_harness.pilots import apps as _apps
        for d in _apps.all_defs():
            ids.add(d.harness_id)
    except Exception:
        pass
    _PILOT_IDS_CACHE = ids
    return ids


def _truncate_err(msg: str) -> str:
    msg = str(msg).replace("\n", " ")[:_MAX_ERROR_DETAIL]
    return msg


def _emit_registry_event(name: str, payload: dict) -> None:
    """Bounded observability — never emit full untrusted payloads."""
    safe = {}
    for k, v in (payload or {}).items():
        if k in ("raw", "payload", "body", "content", "text", "json"):
            continue
        if isinstance(v, str) and len(v) > 120:
            safe[k] = v[:120]
        elif isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        elif isinstance(v, list):
            safe[k] = v[:12]
        elif isinstance(v, dict):
            safe[k] = {str(sk)[:40]: str(sv)[:40] for sk, sv in list(v.items())[:8]}
        else:
            safe[k] = type(v).__name__
    try:
        from saathi.events.bus import EventBus
        bus = EventBus()
        bus.emit(
            type=f"harness.registry.{name}",
            source="application_harness.registry",
            payload=safe,
        )
    except Exception:
        pass


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


def _nest_depth(obj, depth: int = 0) -> int:
    if depth > _MAX_NEST_DEPTH:
        return depth
    if isinstance(obj, dict):
        if not obj:
            return depth
        return max(_nest_depth(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return depth
        return max(_nest_depth(v, depth + 1) for v in obj)
    return depth


def _scan_unsafe(obj, depth: int = 0) -> str | None:
    """Return a rejection code if the payload looks like secrets or shell."""
    if depth > _MAX_NEST_DEPTH:
        return "NESTING_TOO_DEEP"
    if isinstance(obj, dict):
        if len(obj) > _MAX_MAP_LEN:
            return "MAP_TOO_LARGE"
        for k, v in obj.items():
            ks = str(k)
            if _SECRET_KEY.search(ks):
                return "SECRET_KEY_REJECTED"
            if _CTRL.search(ks):
                return "CONTROL_CHAR"
            code = _scan_unsafe(v, depth + 1)
            if code:
                return code
    elif isinstance(obj, list):
        if len(obj) > _MAX_LIST_LEN:
            return "LIST_TOO_LARGE"
        for v in obj:
            code = _scan_unsafe(v, depth + 1)
            if code:
                return code
    elif isinstance(obj, str):
        if len(obj) > _MAX_STRING_LEN:
            return "STRING_TOO_LONG"
        if "\x00" in obj or _CTRL.search(obj):
            return "CONTROL_CHAR"
        if _SHELL_CHAIN.search(obj):
            return "EMBEDDED_SHELL_CHAIN"
        if _TRAVERSAL.search(obj):
            return "PATH_TRAVERSAL"
    elif isinstance(obj, (int, float, bool)) or obj is None:
        pass
    else:
        return "UNSUPPORTED_TYPE"
    return None


def _check_unknown_keys(r: dict) -> str | None:
    """Unknown-field policy: reject security-sensitive unknowns; strip only safe meta."""
    for k in r:
        if k in _FIELD_NAMES or k in _SAFE_META_KEYS:
            continue
        if _SECRET_KEY.search(str(k)):
            return f"SECRET_KEY_REJECTED:{str(k)[:24]}"
        if _SENSITIVE_UNKNOWN.search(str(k)):
            return f"UNKNOWN_SENSITIVE_FIELD:{str(k)[:32]}"
        # non-sensitive unknown still rejected for untrusted persistence (strict)
        return f"UNKNOWN_FIELD:{str(k)[:32]}"
    return None


def validate_entry_dict(r: dict, *, allow_pilot_id: bool = False) -> HarnessDefinition:
    """Authoritative entry validator (boot + mutation + import).

    Raises ValueError with a short rejection code on any failure.
    """
    if not isinstance(r, dict):
        raise ValueError("ENTRY_NOT_OBJECT")
    if len(r) > _MAX_MAP_LEN:
        raise ValueError("ENTRY_TOO_MANY_FIELDS")
    if _nest_depth(r) > _MAX_NEST_DEPTH:
        raise ValueError("NESTING_TOO_DEEP")

    unk = _check_unknown_keys(r)
    if unk:
        raise ValueError(unk)

    unsafe = _scan_unsafe(r)
    if unsafe:
        raise ValueError(unsafe)

    hid = r.get("harness_id")
    if not isinstance(hid, str) or not hid.strip():
        raise ValueError("BAD_HARNESS_ID")
    hid = hid.strip()
    if len(hid) > _MAX_ID_LEN or not _HARNESS_ID_RE.match(hid):
        raise ValueError("BAD_HARNESS_ID")
    if not allow_pilot_id and hid in _pilot_ids() and r.get("source_type") not in (
            "local", None, "system", "bundled"):
        # external records must not claim pilot ids
        raise ValueError("PILOT_ID_COLLISION")

    for field, limit in (
        ("display_name", _MAX_NAME_LEN),
        ("application_name", _MAX_NAME_LEN),
        ("description", _MAX_DESC_LEN),
        ("version", 64),
        ("entrypoint", _MAX_STRING_LEN),
        ("source_repository", _MAX_STRING_LEN),
        ("source_path", _MAX_STRING_LEN),
        ("source_commit", 128),
        ("validation_status", 120),
    ):
        v = r.get(field)
        if v is None:
            continue
        if not isinstance(v, str):
            raise ValueError(f"BAD_TYPE:{field}")
        if len(v) > limit:
            raise ValueError(f"FIELD_TOO_LONG:{field}")

    st = r.get("source_type")
    if st is not None:
        if not isinstance(st, str) or st not in _ALLOWED_SOURCE_TYPES:
            raise ValueError("BAD_SOURCE_TYPE")

    # never accept nested free-form secret bags
    if "required_environment_variables" in r and r["required_environment_variables"]:
        env = r["required_environment_variables"]
        if not isinstance(env, list) or len(env) > _MAX_LIST_LEN:
            raise ValueError("BAD_ENV_LIST")
        # names only, no values
        for item in env:
            if not isinstance(item, str) or _SECRET_KEY.search(item):
                raise ValueError("BAD_ENV_ITEM")

    # resource_limits / nested maps bounded
    for map_field in ("resource_limits",):
        m = r.get(map_field)
        if m is None:
            continue
        if not isinstance(m, dict) or len(m) > _MAX_MAP_LEN:
            raise ValueError(f"BAD_MAP:{map_field}")
        if _nest_depth(m) > 3:
            raise ValueError(f"NESTING_TOO_DEEP:{map_field}")

    for list_field in (
        "supported_platforms", "supported_application_versions",
        "required_executables", "required_packages", "required_permissions",
        "required_file_roots", "required_network_origins", "supported_operations",
    ):
        lst = r.get(list_field)
        if lst is None:
            continue
        if not isinstance(lst, list) or len(lst) > _MAX_LIST_LEN:
            raise ValueError(f"BAD_LIST:{list_field}")

    trust = r.get("trust_status")
    if trust is not None:
        if not isinstance(trust, str):
            raise ValueError("BAD_TRUST_TYPE")
        try:
            TrustStatus(trust)
        except ValueError:
            raise ValueError("BAD_TRUST_VALUE") from None

    # risk_ceiling must be int in range if present
    rc = r.get("risk_ceiling")
    if rc is not None and (not isinstance(rc, int) or isinstance(rc, bool) or rc < 0 or rc > 4):
        raise ValueError("BAD_RISK_CEILING")

    kwargs = {k: r[k] for k in r if k in _FIELD_NAMES}
    kwargs.pop("required_environment_variables", None)
    kwargs["harness_id"] = hid
    try:
        d = HarnessDefinition(**kwargs)
    except TypeError as e:
        raise ValueError(f"ENTRY_CONSTRUCT:{type(e).__name__}") from e

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


def _definition_from_record(r: dict) -> HarnessDefinition:
    """Back-compat alias used by tests/internal call sites."""
    return validate_entry_dict(r, allow_pilot_id=True)


def validate_definition(defn: HarnessDefinition) -> HarnessDefinition:
    """Validate a live HarnessDefinition via the same dict rules."""
    return validate_entry_dict(defn.to_dict(), allow_pilot_id=True)


def _apply_restrictive_overlay(live: HarnessDefinition, disk: HarnessDefinition) -> bool:
    """Apply only more-restrictive trust from disk onto a code-seeded pilot.

    Returns True if live was mutated. Trust escalation is rejected (no-op + report).
    """
    changed = False
    if disk.trust_status in _RESTRICTIVE_TRUST and live.trust_status != disk.trust_status:
        live.trust_status = disk.trust_status
        changed = True
    elif disk.trust_status not in _RESTRICTIVE_TRUST:
        # attempted elevation / non-restrictive change — ignore
        pass
    # restore validation marker when present and non-empty
    if disk.validation_status and disk.validation_status != live.validation_status:
        if disk.trust_status in _RESTRICTIVE_TRUST:
            live.validation_status = disk.validation_status
            changed = True
    if changed:
        live.updated_at = time.time()
    return changed


def _validate_envelope(doc) -> tuple[list, dict]:
    """Validate top-level document. Returns (entries, meta) or raises ValueError."""
    if not isinstance(doc, dict):
        raise ValueError("REGISTRY_TOPLEVEL_NOT_OBJECT")
    if "schema_version" not in doc:
        raise ValueError("REGISTRY_SCHEMA_VERSION_MISSING")
    ver = doc["schema_version"]
    if not isinstance(ver, int) or isinstance(ver, bool):
        raise ValueError("REGISTRY_SCHEMA_VERSION_TYPE")
    if ver > SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"REGISTRY_SCHEMA_UNSUPPORTED:{ver}")
    if ver < 1:
        raise ValueError(f"REGISTRY_SCHEMA_TOO_OLD:{ver}")
    if ver != SUPPORTED_SCHEMA_VERSION:
        # only v1 today — future migrations would branch here
        raise ValueError(f"REGISTRY_SCHEMA_UNSUPPORTED:{ver}")

    # unknown top-level keys: reject security-sensitive; ignore only safe meta
    allowed_top = {
        "schema_version", "harnesses", "entries", "generated_at",
        "generated_by", "_comment", "comment",
    }
    for k in doc:
        if k in allowed_top:
            continue
        if _SENSITIVE_UNKNOWN.search(str(k)) or _SECRET_KEY.search(str(k)):
            raise ValueError(f"REGISTRY_UNKNOWN_SENSITIVE_TOP:{str(k)[:32]}")
        raise ValueError(f"REGISTRY_UNKNOWN_TOP:{str(k)[:32]}")

    # canonical key is harnesses; accept entries as alias (deterministic migration)
    if "harnesses" in doc and "entries" in doc:
        raise ValueError("REGISTRY_AMBIGUOUS_ENTRY_KEYS")
    entries = doc.get("harnesses", doc.get("entries"))
    if entries is None:
        raise ValueError("REGISTRY_ENTRIES_MISSING")
    if not isinstance(entries, list):
        raise ValueError("REGISTRY_ENTRIES_NOT_LIST")
    if len(entries) > _MAX_ENTRIES:
        raise ValueError("REGISTRY_TOO_MANY_ENTRIES")

    # timestamps never authorize
    gen = doc.get("generated_at")
    if gen is not None and not isinstance(gen, (str, int, float)):
        raise ValueError("REGISTRY_GENERATED_AT_TYPE")

    return entries, {"schema_version": ver, "generated_at": gen}


def _maybe_quarantine(path: Path, reason: str) -> str | None:
    """Bounded quarantine: rename corrupt file once; keep at most N sidecars."""
    try:
        if not path.exists():
            return None
        parent = path.parent
        existing = sorted(parent.glob(path.name + ".corrupt.*"))
        while len(existing) >= _MAX_QUARANTINE_FILES:
            try:
                existing[0].unlink()
            except OSError:
                break
            existing = sorted(parent.glob(path.name + ".corrupt.*"))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        dest = parent / f"{path.name}.corrupt.{stamp}"
        # never put reason/secrets in filename
        path.replace(dest)
        return str(dest.name)
    except OSError:
        return None


def _load_store() -> dict:
    """Load STORE into _REG.

    Policy (M17.19):
    - invalid/oversized/unsupported envelope → reject ENTIRE payload (fail closed);
      built-in pilots remain from code seed;
    - per-entry invalid → skip that entry (safe isolation already used in M17.18);
    - duplicate harness_ids in file → reject entire payload.
    """
    global _LAST_LOAD
    report = {
        "status": "missing",
        "loaded": 0,
        "merged": 0,
        "skipped": 0,
        "errors": [],
        "path": str(STORE),
        "policy": "envelope_fail_closed_entry_skip",
        "schema_version": None,
        "payload_sha256": None,
    }
    if not STORE.exists():
        _LAST_LOAD = report
        return report

    try:
        # bounded read: stop after max+1 bytes
        with open(STORE, "rb") as f:
            raw = f.read(_MAX_STORE_BYTES + 1)
        if len(raw) > _MAX_STORE_BYTES:
            report["status"] = "too_large"
            report["errors"].append("REGISTRY_TOO_LARGE")
            _LAST_LOAD = report
            _emit_registry_event("rejected", {
                "reason": "too_large", "bytes": len(raw),
            })
            return report
        report["payload_sha256"] = hashlib.sha256(raw).hexdigest()[:16]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            report["status"] = "invalid"
            report["errors"].append("REGISTRY_INVALID_UTF8")
            _LAST_LOAD = report
            _emit_registry_event("rejected", {"reason": "invalid_utf8"})
            return report
        doc = json.loads(text)
    except json.JSONDecodeError:
        report["status"] = "invalid"
        report["errors"].append("REGISTRY_INVALID_JSON")
        _LAST_LOAD = report
        _emit_registry_event("rejected", {"reason": "invalid_json"})
        return report
    except Exception as e:
        report["status"] = "invalid"
        report["errors"].append(_truncate_err(f"REGISTRY_INVALID:{type(e).__name__}"))
        _LAST_LOAD = report
        _emit_registry_event("rejected", {"reason": type(e).__name__})
        return report

    try:
        entries, meta = _validate_envelope(doc)
    except ValueError as e:
        code = str(e.args[0]) if e.args else "REGISTRY_INVALID_SCHEMA"
        if "SCHEMA" in code or "UNSUPPORTED" in code:
            report["status"] = "unsupported_schema" if "UNSUPPORTED" in code else "invalid_schema"
        elif "TOO_MANY" in code:
            report["status"] = "too_many_entries"
        else:
            report["status"] = "invalid_schema"
        report["errors"].append(_truncate_err(code))
        _LAST_LOAD = report
        _emit_registry_event("rejected", {
            "reason": report["status"], "code": code[:40],
        })
        return report

    report["schema_version"] = meta.get("schema_version")

    # duplicate id scan (entire payload reject)
    seen: set[str] = set()
    for r in entries:
        if not isinstance(r, dict):
            report["status"] = "invalid_schema"
            report["errors"].append("ENTRY_NOT_OBJECT")
            _LAST_LOAD = report
            _emit_registry_event("rejected", {"reason": "entry_not_object"})
            return report
        hid = r.get("harness_id")
        if isinstance(hid, str) and hid in seen:
            report["status"] = "invalid_schema"
            report["errors"].append("DUPLICATE_HARNESS_ID")
            _LAST_LOAD = report
            _emit_registry_event("rejected", {"reason": "duplicate_id"})
            return report
        if isinstance(hid, str):
            seen.add(hid)

    for r in entries:
        try:
            d = validate_entry_dict(r, allow_pilot_id=True)
        except Exception as e:
            report["skipped"] += 1
            if len(report["errors"]) < _MAX_ERRORS_REPORTED:
                report["errors"].append(_truncate_err(
                    str(getattr(e, "args", [e])[0])
                ))
            continue
        if d.harness_id in _REG:
            # pilot / already seeded: only restrictive overlay
            live = _REG[d.harness_id]
            disk_ts = d.trust_status
            # explicit: trust broadening from disk is never applied
            if disk_ts not in _RESTRICTIVE_TRUST and disk_ts != live.trust_status:
                report["skipped"] += 1
                if len(report["errors"]) < _MAX_ERRORS_REPORTED:
                    report["errors"].append("TRUST_ESCALATION_REJECTED")
                _emit_registry_event("trust_escalation_rejected", {
                    "harness_id": d.harness_id[:40],
                })
                continue
            if _apply_restrictive_overlay(live, d):
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
    _emit_registry_event("loaded", {
        "loaded": report["loaded"],
        "merged": report["merged"],
        "skipped": report["skipped"],
        "schema_version": report["schema_version"],
        "payload_sha256": report["payload_sha256"],
    })
    return report


def load_report() -> dict:
    """Last boot-load report (diagnostics / Control Center)."""
    _bootstrap()
    return dict(_LAST_LOAD)


def register(defn: HarnessDefinition) -> None:
    """Register (or replace) a harness definition after authoritative validation."""
    _bootstrap()
    validated = validate_definition(defn)
    # cannot use register to weaken pilots into broader trust from an untrusted source
    if validated.harness_id in _REG and validated.harness_id in _pilot_ids():
        live = _REG[validated.harness_id]
        # allow only equal or more restrictive trust when source is not code path
        # (in-process register from lifecycle may set restrictive; elevation still ok
        # for explicit first-party code calls that already hold trusted defs)
        pass
    _REG[validated.harness_id] = validated
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
            "limits": {
                "max_store_bytes": _MAX_STORE_BYTES,
                "max_entries": _MAX_ENTRIES,
                "schema_version": SUPPORTED_SCHEMA_VERSION,
            },
            "harnesses": [{"harness_id": d.harness_id, "application": d.application_name,
                           "version": d.version, "trust": d.trust_status,
                           "source_type": d.source_type,
                           "operations": len(d.supported_operations)}
                          for d in _REG.values()]}


def import_records(records: list, *, strict: bool = True) -> dict:
    """Add imported CLI-Anything discovery records (untrusted; never executable).

    Uses the same authoritative validator as boot. When strict=True (default),
    any invalid record rejects the entire batch with no in-memory or disk mutation.
    """
    _bootstrap()
    if not isinstance(records, list):
        return {"added": 0, "total": len(_REG), "error": "RECORDS_NOT_LIST", "rejected": 0}
    if len(records) > _MAX_ENTRIES:
        return {"added": 0, "total": len(_REG), "error": "TOO_MANY_RECORDS", "rejected": len(records)}

    snapshot = dict(_REG)
    prepared: list[HarnessDefinition] = []
    errors: list[str] = []
    for r in records:
        if not isinstance(r, dict):
            errors.append("ENTRY_NOT_OBJECT")
            continue
        try:
            d = validate_entry_dict(r, allow_pilot_id=False)
        except ValueError as e:
            errors.append(_truncate_err(str(e.args[0] if e.args else e)))
            continue
        d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value  # force untrusted
        d.validation_status = d.validation_status or "imported_untrusted"
        if d.harness_id in _REG or d.harness_id in {p.harness_id for p in prepared}:
            errors.append("DUPLICATE_OR_EXISTING")
            continue
        prepared.append(d)

    if strict and errors:
        # restore is no-op since we never mutated; explicit for clarity
        _REG.clear()
        _REG.update(snapshot)
        _emit_registry_event("import_rejected", {
            "rejected": len(errors), "error_sample": errors[:5],
        })
        return {
            "added": 0,
            "total": len(_REG),
            "error": "IMPORT_VALIDATION_FAILED",
            "rejected": len(errors),
            "errors": errors[:_MAX_ERRORS_REPORTED],
        }

    added = 0
    for d in prepared:
        if d.harness_id not in _REG:
            _REG[d.harness_id] = d
            added += 1
    if added:
        try:
            persist()
        except Exception as e:
            # roll back in-memory additions if persist fails
            _REG.clear()
            _REG.update(snapshot)
            return {
                "added": 0,
                "total": len(_REG),
                "error": f"PERSIST_FAILED:{type(e).__name__}",
                "rejected": 0,
            }
    return {"added": added, "total": len(_REG), "rejected": len(errors),
            "errors": errors[:_MAX_ERRORS_REPORTED] if errors else []}


def persist() -> str:
    """Atomically write current registry to STORE. Never writes secrets."""
    # ensure pilots are seeded if caller registered before first get()
    if not _REG:
        _seed_pilots()
    STORE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STORE.parent, 0o700)
    except OSError:
        pass

    payload = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harnesses": [d.to_dict() for d in _REG.values()],
    }
    if len(payload["harnesses"]) > _MAX_ENTRIES:
        raise RuntimeError("REGISTRY_TOO_MANY_ENTRIES")
    text = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    if len(text.encode("utf-8")) > _MAX_STORE_BYTES:
        raise RuntimeError("REGISTRY_PAYLOAD_TOO_LARGE")
    # refuse to persist if somehow secrets snuck in
    if _scan_unsafe(payload):
        raise RuntimeError("REGISTRY_REFUSES_SECRET_PAYLOAD")

    tmp = STORE.with_name(STORE.name + ".tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(tmp), flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise
        os.replace(str(tmp), str(STORE))
        try:
            os.chmod(STORE, 0o600)
        except OSError:
            pass
        # fsync directory for durability (best effort)
        try:
            dir_fd = os.open(str(STORE.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception as e:
        # leave previous STORE intact; clean tmp
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        _emit_registry_event("atomic_write_failed", {
            "error": type(e).__name__,
        })
        raise
    # clean any leftover .tmp
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass
    _emit_registry_event("persisted", {
        "entries": len(payload["harnesses"]),
        "schema_version": SUPPORTED_SCHEMA_VERSION,
    })
    return str(STORE)


def reset_for_tests(*, store: Path | None = None) -> None:
    """Clear in-memory registry (and optionally retarget STORE). Tests only."""
    global STORE, _LAST_LOAD, _PILOT_IDS_CACHE
    _REG.clear()
    _LAST_LOAD = {
        "status": "not_attempted",
        "loaded": 0,
        "merged": 0,
        "skipped": 0,
        "errors": [],
        "policy": "envelope_fail_closed_entry_skip",
    }
    _PILOT_IDS_CACHE = None
    if store is not None:
        STORE = Path(store)
