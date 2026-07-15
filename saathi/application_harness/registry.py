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

M17.20: multi-writer concurrency — process-safe fcntl file lock + in-process
RLock, durable revision CAS, lock→reload→mutate→atomic-write→release for
register/import, bounded lock timeout, applied_ops idempotency, no second
registry or distributed consensus.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
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

# ── M17.20 concurrency (local-first; not multi-host consensus) ───────────────
_LOCK_TIMEOUT_SEC = 5.0
_LOCK_POLL_SEC = 0.05
_MAX_APPLIED_OPS = 64
_THREAD_LOCK = threading.RLock()
_OWNER_ID = f"pid{os.getpid()}-{uuid.uuid4().hex[:8]}"

_REG: dict[str, HarnessDefinition] = {}
_LAST_LOAD: dict = {
    "status": "not_attempted",
    "loaded": 0,
    "merged": 0,
    "skipped": 0,
    "errors": [],
    "policy": "envelope_fail_closed_entry_skip",
}
_LOADED_REVISION = 0
_APPLIED_OPS: list[str] = []
_HOLDING_WRITE_LOCK = False

# M17.21 operational diagnostics (bounded; never store payloads/secrets)
_HEALTH_DIAG: dict = {
    "last_load_time": None,
    "last_successful_write": None,
    "last_validation": None,
    "last_atomic_write": None,
    "last_conflict": None,
    "last_recovery": None,
    "failed_validations": 0,
    "last_validation_status": None,
    "warnings": [],
}
_CEO_BRIEF_SCORE_THRESHOLD = 80  # suppress brief noise when GREEN and score ≥ this


class RegistryBusy(RuntimeError):
    """Lock acquisition timed out — no mutation applied."""


class RegistryConflict(RuntimeError):
    """Stale revision or incompatible concurrent mutation — no overwrite."""

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


def _note_health(kind: str, detail: str | None = None) -> None:
    """Update bounded health diagnostics from operational events."""
    now = time.time()
    if kind in ("loaded", "rejected", "invalid", "too_large", "unsupported_schema"):
        _HEALTH_DIAG["last_load_time"] = now
        _HEALTH_DIAG["last_validation"] = now
        _HEALTH_DIAG["last_validation_status"] = kind
        if kind not in ("loaded",):
            _HEALTH_DIAG["failed_validations"] = int(
                _HEALTH_DIAG.get("failed_validations") or 0
            ) + 1
    if kind in ("write_committed", "persisted"):
        _HEALTH_DIAG["last_successful_write"] = now
        _HEALTH_DIAG["last_atomic_write"] = now
    if kind in ("atomic_write_failed", "write_failed"):
        _HEALTH_DIAG["last_atomic_write"] = now
        _HEALTH_DIAG["failed_validations"] = int(
            _HEALTH_DIAG.get("failed_validations") or 0
        ) + 1
    if kind in ("revision_conflict",) or "conflict" in kind:
        _HEALTH_DIAG["last_conflict"] = {
            "at": now, "kind": kind, "detail": (detail or "")[:80],
        }
    if kind in ("stale_lock_recovered",):
        _HEALTH_DIAG["last_recovery"] = {
            "at": now, "kind": kind, "detail": (detail or "")[:80],
        }
    warns = list(_HEALTH_DIAG.get("warnings") or [])
    if kind in (
        "write_lock_timeout", "revision_conflict", "atomic_write_failed",
        "rejected", "too_large", "unsupported_schema",
    ):
        warns.append({"at": now, "kind": kind})
        _HEALTH_DIAG["warnings"] = warns[-12:]


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
        _note_health(name, str(safe.get("reason") or safe.get("code") or "")[:80])
    except Exception:
        pass
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
        # M17.20 concurrency metadata (never authorize trust)
        "revision", "applied_ops",
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

    rev = doc.get("revision", 0)
    if rev is None:
        rev = 0
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 0:
        raise ValueError("REGISTRY_REVISION_TYPE")
    ops = doc.get("applied_ops", [])
    if ops is None:
        ops = []
    if not isinstance(ops, list) or len(ops) > _MAX_APPLIED_OPS:
        raise ValueError("REGISTRY_APPLIED_OPS_INVALID")
    for op in ops:
        if not isinstance(op, str) or len(op) > 120:
            raise ValueError("REGISTRY_APPLIED_OPS_INVALID")

    return entries, {
        "schema_version": ver,
        "generated_at": gen,
        "revision": rev,
        "applied_ops": list(ops),
    }


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
    global _LAST_LOAD, _LOADED_REVISION, _APPLIED_OPS
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
        "revision": 0,
    }
    if not STORE.exists():
        _LOADED_REVISION = 0
        _APPLIED_OPS = []
        _LAST_LOAD = report
        return report

    try:
        # bounded read: stop after max+1 bytes (never read tmp; only STORE)
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
    report["revision"] = int(meta.get("revision") or 0)
    _LOADED_REVISION = report["revision"]
    _APPLIED_OPS = list(meta.get("applied_ops") or [])

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
    _note_health("loaded")
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


def current_revision() -> int:
    """Last loaded/committed registry revision (0 if no durable state)."""
    _bootstrap()
    return int(_LOADED_REVISION)


def _lock_path() -> Path:
    return STORE.with_name(STORE.name + ".lock")


def _read_disk_revision() -> int:
    """Read revision from durable STORE only (never .tmp). Fail-closed → 0."""
    if not STORE.exists():
        return 0
    try:
        with open(STORE, "rb") as f:
            raw = f.read(_MAX_STORE_BYTES + 1)
        if len(raw) > _MAX_STORE_BYTES:
            return 0
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            return 0
        rev = doc.get("revision", 0)
        if isinstance(rev, int) and not isinstance(rev, bool) and rev >= 0:
            return rev
    except Exception:
        return 0
    return 0


def _read_disk_applied_ops() -> list[str]:
    if not STORE.exists():
        return []
    try:
        with open(STORE, "rb") as f:
            raw = f.read(_MAX_STORE_BYTES + 1)
        doc = json.loads(raw.decode("utf-8"))
        ops = doc.get("applied_ops") or []
        if isinstance(ops, list):
            return [str(x) for x in ops if isinstance(x, str)][:_MAX_APPLIED_OPS]
    except Exception:
        return []
    return []


@contextmanager
def _registry_write_lock(timeout: float | None = None):
    """Acquire in-process RLock + process-safe exclusive flock.

    fcntl locks are released on process death (no permanent stale flock).
    Metadata in the lock file is best-effort observability only.
    """
    global _HOLDING_WRITE_LOCK
    timeout = _LOCK_TIMEOUT_SEC if timeout is None else float(timeout)
    t0 = time.monotonic()
    got_thread = _THREAD_LOCK.acquire(timeout=timeout)
    if not got_thread:
        _emit_registry_event("write_lock_timeout", {"scope": "thread"})
        raise RegistryBusy("LOCK_TIMEOUT")
    remaining = max(0.01, timeout - (time.monotonic() - t0))
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + remaining
    contended = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                contended = True
                if time.monotonic() >= deadline:
                    _emit_registry_event("write_lock_timeout", {"scope": "file"})
                    raise RegistryBusy("LOCK_TIMEOUT") from None
                _emit_registry_event("write_lock_contended", {})
                time.sleep(_LOCK_POLL_SEC)
        if contended:
            # prior owner may have crashed; flock free ⇒ recover (kernel released)
            _emit_registry_event("stale_lock_recovered", {
                "note": "flock_free_after_contention",
            })
        meta = json.dumps({
            "owner": _OWNER_ID,
            "pid": os.getpid(),
            "acquired_at": time.time(),
        }, separators=(",", ":"))
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, meta.encode("utf-8")[:512])
            os.fsync(fd)
        except OSError:
            pass
        _HOLDING_WRITE_LOCK = True
        _emit_registry_event("write_lock_acquired", {"owner": _OWNER_ID[:40]})
        yield
    finally:
        _HOLDING_WRITE_LOCK = False
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _THREAD_LOCK.release()
        except RuntimeError:
            pass


def _reload_committed_locked() -> int:
    """Under write lock: rebuild memory from pilots + durable STORE. Returns revision."""
    global _LOADED_REVISION, _APPLIED_OPS
    _REG.clear()
    _seed_pilots()
    _load_store()
    return int(_LOADED_REVISION)


def _persist_locked(
    *,
    expected_revision: int | None = None,
    operation_id: str | None = None,
) -> str:
    """Atomic write under write lock. CAS on expected_revision when provided."""
    global _LOADED_REVISION, _APPLIED_OPS
    if not _REG:
        _seed_pilots()
    STORE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STORE.parent, 0o700)
    except OSError:
        pass

    disk_rev = _read_disk_revision()
    if expected_revision is not None and disk_rev != expected_revision:
        _emit_registry_event("revision_conflict", {
            "expected": expected_revision, "disk": disk_rev,
        })
        raise RegistryConflict(
            f"STALE_REVISION:expected={expected_revision}:disk={disk_rev}"
        )

    new_rev = disk_rev + 1
    ops = list(_read_disk_applied_ops())
    if operation_id:
        if operation_id in ops:
            _emit_registry_event("mutation_deduplicated", {
                "operation_id": operation_id[:40],
            })
            # already applied on disk — refresh memory and no-op write skip
            _reload_committed_locked()
            return str(STORE)
        ops.append(operation_id)
        ops = ops[-_MAX_APPLIED_OPS:]

    payload = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revision": new_rev,
        "applied_ops": ops,
        "harnesses": [d.to_dict() for d in _REG.values()],
    }
    if len(payload["harnesses"]) > _MAX_ENTRIES:
        raise RuntimeError("REGISTRY_TOO_MANY_ENTRIES")
    text = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    if len(text.encode("utf-8")) > _MAX_STORE_BYTES:
        raise RuntimeError("REGISTRY_PAYLOAD_TOO_LARGE")
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
        try:
            dir_fd = os.open(str(STORE.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception as e:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        _emit_registry_event("write_failed", {"error": type(e).__name__})
        _emit_registry_event("atomic_write_failed", {"error": type(e).__name__})
        raise
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass

    _LOADED_REVISION = new_rev
    _APPLIED_OPS = ops
    _emit_registry_event("write_committed", {
        "revision": new_rev,
        "entries": len(payload["harnesses"]),
        "schema_version": SUPPORTED_SCHEMA_VERSION,
    })
    _emit_registry_event("persisted", {
        "entries": len(payload["harnesses"]),
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "revision": new_rev,
    })
    return str(STORE)


def register(
    defn: HarnessDefinition,
    *,
    operation_id: str | None = None,
) -> dict:
    """Register after validation under the authoritative write lock.

    Flow: validate → lock → reload durable state → re-check conflicts →
    apply → atomic persist (revision CAS) → unlock.
    """
    _bootstrap()
    validated = validate_definition(defn)
    op = operation_id or f"reg:{validated.harness_id}:{validated.version}:{validated.trust_status}"
    try:
        with _registry_write_lock():
            base = _reload_committed_locked()
            if op in _APPLIED_OPS or op in _read_disk_applied_ops():
                _emit_registry_event("mutation_deduplicated", {"operation_id": op[:40]})
                return {
                    "ok": True,
                    "deduplicated": True,
                    "revision": _LOADED_REVISION,
                    "harness_id": validated.harness_id,
                }
            existing = _REG.get(validated.harness_id)
            if existing is not None and existing.harness_id in _pilot_ids():
                # may only apply restrictive trust overlay; never replace pilot body
                if validated.trust_status in _RESTRICTIVE_TRUST:
                    _apply_restrictive_overlay(existing, validated)
                elif (
                    existing.trust_status != validated.trust_status
                    or existing.version != validated.version
                    or existing.description != validated.description
                ):
                    # non-restrictive change to pilot → conflict (no replace)
                    raise RegistryConflict("PILOT_REPLACE_CONFLICT")
            elif existing is not None:
                # same-id update: allow only if identical or more restrictive trust
                if (
                    existing.version != validated.version
                    or existing.source_type != validated.source_type
                    or existing.display_name != validated.display_name
                ):
                    # incompatible concurrent update
                    if existing.to_dict() != validated.to_dict():
                        # identical content would be fine; different body conflicts
                        same = (
                            existing.version == validated.version
                            and existing.trust_status == validated.trust_status
                            and existing.source_type == validated.source_type
                        )
                        if not same:
                            raise RegistryConflict("UPDATE_CONFLICT")
                _REG[validated.harness_id] = validated
            else:
                _REG[validated.harness_id] = validated
            path = _persist_locked(expected_revision=base, operation_id=op)
            return {
                "ok": True,
                "deduplicated": False,
                "revision": _LOADED_REVISION,
                "harness_id": validated.harness_id,
                "store": path,
            }
    except RegistryBusy:
        raise
    except RegistryConflict:
        raise
    except Exception:
        # ensure memory matches last committed on unexpected failure mid-flight
        try:
            with _registry_write_lock(timeout=min(2.0, _LOCK_TIMEOUT_SEC)):
                _reload_committed_locked()
        except Exception:
            pass
        raise


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
            "revision": _LOADED_REVISION,
            "limits": {
                "max_store_bytes": _MAX_STORE_BYTES,
                "max_entries": _MAX_ENTRIES,
                "schema_version": SUPPORTED_SCHEMA_VERSION,
                "lock_timeout_sec": _LOCK_TIMEOUT_SEC,
            },
            "harnesses": [{"harness_id": d.harness_id, "application": d.application_name,
                           "version": d.version, "trust": d.trust_status,
                           "source_type": d.source_type,
                           "operations": len(d.supported_operations)}
                          for d in _REG.values()]}


def _registry_critical_inventory() -> tuple[int, list[str]]:
    """Count blocking registry.* checks in the critical manifest (no pytest run)."""
    try:
        from saathi.repair.manifest import load_manifest
        ids = [
            c.id for c in load_manifest()
            if str(getattr(c, "id", "")).startswith("registry.")
            and getattr(c, "blocking", True)
        ]
        return len(ids), ids
    except Exception:
        return 0, []


def _quarantine_count() -> int:
    try:
        parent = STORE.parent
        if not parent.exists():
            return 0
        return len(list(parent.glob(STORE.name + ".corrupt.*")))
    except Exception:
        return 0


def _score_and_status(signals: dict) -> tuple[int, str, list[str]]:
    """Deterministic health score (0–100) and status. No LLM."""
    score = 100
    reasons: list[str] = []
    load_st = signals.get("load_status") or "not_attempted"
    if load_st in ("invalid", "invalid_schema", "unsupported_schema", "too_large",
                   "too_many_entries"):
        score -= 40
        reasons.append(f"load:{load_st}")
    if load_st == "unsupported_schema":
        score -= 10
        reasons.append("schema_mismatch")
    skipped = int(signals.get("skipped") or 0)
    if skipped:
        pen = min(20, skipped * 2)
        score -= pen
        reasons.append(f"skipped_entries:{skipped}")
    if signals.get("failed_validations"):
        pen = min(15, int(signals["failed_validations"]) * 3)
        score -= pen
        reasons.append("failed_validations")
    size = int(signals.get("registry_size_bytes") or 0)
    limit = int(signals.get("size_limit") or _MAX_STORE_BYTES)
    if limit > 0:
        ratio = size / limit
        if ratio >= 1.0:
            score -= 25
            reasons.append("oversized")
        elif ratio >= 0.95:
            score -= 15
            reasons.append("near_size_limit")
        elif ratio >= 0.80:
            score -= 10
            reasons.append("size_warning")
    if signals.get("last_conflict"):
        score -= 10
        reasons.append("conflict")
    if signals.get("last_recovery"):
        score -= 5
        reasons.append("recovery")
    if signals.get("lock_state") == "held":
        score -= 5
        reasons.append("lock_held")
    if int(signals.get("quarantined_files") or 0) > 0:
        score -= min(15, 5 * int(signals["quarantined_files"]))
        reasons.append("quarantine")
    green = int(signals.get("critical_checks_green") or 0)
    total = int(signals.get("critical_checks_total") or 0)
    if total and green < total:
        # operational proxy: if load broken, treat checks as not green
        score -= min(20, (total - green) * 2)
        reasons.append("critical_checks")
    if signals.get("schema_mismatch"):
        score -= 15
        if "schema_mismatch" not in reasons:
            reasons.append("schema_mismatch")
    if signals.get("atomic_write_failed_recent"):
        score -= 20
        reasons.append("atomic_write_failed")
    score = max(0, min(100, score))
    if score < 40 or load_st in ("invalid", "unsupported_schema", "too_large"):
        status = "RED"
    elif score < 60:
        status = "ORANGE"
    elif score < 80:
        status = "YELLOW"
    else:
        status = "GREEN"
    return score, status, reasons


def health() -> dict:
    """M17.21 authoritative registry health object (read-only, safe summaries).

    Never includes registry payload, credentials, or raw untrusted JSON.
    Health score is deterministic (no LLM).
    """
    _bootstrap()
    load = dict(_LAST_LOAD)
    by_trust = {}
    pilots = 0
    active = 0
    disabled = 0
    overlays = 0
    pids = _pilot_ids()
    for d in _REG.values():
        by_trust[d.trust_status] = by_trust.get(d.trust_status, 0) + 1
        if d.harness_id in pids:
            pilots += 1
        if d.trust_status in _RESTRICTIVE_TRUST:
            if d.harness_id in pids:
                overlays += 1
            disabled += 1
        elif d.executable() or d.trust_status not in (
            TrustStatus.REJECTED.value, TrustStatus.REVOKED.value,
            TrustStatus.QUARANTINED.value, TrustStatus.COMPROMISED.value,
        ):
            active += 1
        else:
            disabled += 1
    size = 0
    if STORE.exists():
        try:
            size = int(STORE.stat().st_size)
        except OSError:
            size = 0
    crit_total, crit_ids = _registry_critical_inventory()
    load_st = load.get("status") or "not_attempted"
    # operational proxy for "green" without running pytest each call
    crit_green = crit_total if load_st in ("ok", "missing", "not_attempted") else 0
    schema_mismatch = load_st == "unsupported_schema"
    qcount = _quarantine_count()
    warns = []
    for w in (_HEALTH_DIAG.get("warnings") or [])[-6:]:
        if isinstance(w, dict):
            warns.append({"kind": w.get("kind"), "at": w.get("at")})
    atomic_fail = any(
        (w.get("kind") if isinstance(w, dict) else None) == "atomic_write_failed"
        for w in (_HEALTH_DIAG.get("warnings") or [])[-6:]
    )
    signals = {
        "load_status": load_st,
        "skipped": load.get("skipped") or 0,
        "failed_validations": _HEALTH_DIAG.get("failed_validations") or 0,
        "registry_size_bytes": size,
        "size_limit": _MAX_STORE_BYTES,
        "last_conflict": _HEALTH_DIAG.get("last_conflict"),
        "last_recovery": _HEALTH_DIAG.get("last_recovery"),
        "lock_state": "held" if _HOLDING_WRITE_LOCK else "free",
        "quarantined_files": qcount,
        "critical_checks_green": crit_green,
        "critical_checks_total": crit_total,
        "schema_mismatch": schema_mismatch,
        "atomic_write_failed_recent": atomic_fail,
    }
    score, status, reasons = _score_and_status(signals)
    # last_validation: prefer diagnostics, else load timestamp proxy
    last_val = _HEALTH_DIAG.get("last_validation")
    if last_val is None and load_st not in ("not_attempted",):
        last_val = _HEALTH_DIAG.get("last_load_time")
    out = {
        "overall_status": status,
        "health_score": score,
        "score_reasons": reasons,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "loaded_schema_version": load.get("schema_version"),
        "registry_revision": int(_LOADED_REVISION),
        "built_in_pilots": pilots,
        "persisted_entries": int(load.get("loaded") or 0),
        "active_entries": active,
        "disabled_entries": disabled,
        "trust_overlays": overlays,
        "total_entries": len(_REG),
        "by_trust": by_trust,
        "last_load_time": _HEALTH_DIAG.get("last_load_time"),
        "last_successful_write": _HEALTH_DIAG.get("last_successful_write"),
        "last_validation": last_val,
        "last_atomic_write": _HEALTH_DIAG.get("last_atomic_write"),
        "lock_state": "held" if _HOLDING_WRITE_LOCK else "free",
        "lock_owner": _OWNER_ID if _HOLDING_WRITE_LOCK else None,
        "lock_waiters": 0,  # flock does not expose waiter count
        "last_conflict": _HEALTH_DIAG.get("last_conflict"),
        "last_recovery": _HEALTH_DIAG.get("last_recovery"),
        "failed_validations": int(_HEALTH_DIAG.get("failed_validations") or 0),
        "rejected_entries": int(load.get("skipped") or 0),
        "quarantined_files": qcount,
        "registry_size_bytes": size,
        "entry_limit": _MAX_ENTRIES,
        "size_limit": _MAX_STORE_BYTES,
        "critical_checks_green": crit_green,
        "critical_checks_total": crit_total,
        "critical_check_ids": crit_ids[:32],
        "load_status": load_st,
        "load_errors": list(load.get("errors") or [])[:8],
        "warnings": warns,
        "ceo_brief_threshold": _CEO_BRIEF_SCORE_THRESHOLD,
        "include_in_ceo_brief": status != "GREEN" or score < _CEO_BRIEF_SCORE_THRESHOLD,
    }
    return out


def health_diagnostics() -> dict:
    """Safe diagnostics slice for Control Center drill-down (no secrets/payloads)."""
    h = health()
    return {
        "overall_status": h["overall_status"],
        "health_score": h["health_score"],
        "score_reasons": h["score_reasons"],
        "load_status": h["load_status"],
        "load_errors": h["load_errors"],
        "last_conflict": h["last_conflict"],
        "last_recovery": h["last_recovery"],
        "limits": {
            "entry_limit": h["entry_limit"],
            "size_limit": h["size_limit"],
            "lock_timeout_sec": _LOCK_TIMEOUT_SEC,
        },
        "critical_checks": {
            "green": h["critical_checks_green"],
            "total": h["critical_checks_total"],
            "ids": h["critical_check_ids"],
        },
        "warnings": h["warnings"],
    }


def import_records(
    records: list,
    *,
    strict: bool = True,
    operation_id: str | None = None,
) -> dict:
    """Add imported CLI-Anything discovery records (untrusted; never executable).

    Same write lock as register. strict=True rejects entire batch on any invalid
    record with no mutation. Concurrent imports serialize and re-check latest state.
    """
    _bootstrap()
    if not isinstance(records, list):
        return {"added": 0, "total": len(_REG), "error": "RECORDS_NOT_LIST", "rejected": 0}
    if len(records) > _MAX_ENTRIES:
        return {"added": 0, "total": len(_REG), "error": "TOO_MANY_RECORDS",
                "rejected": len(records)}

    # Pre-validate outside the lock (fail fast; re-validate under lock)
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
        d.trust_status = TrustStatus.EXTERNAL_UNTRUSTED.value
        d.validation_status = d.validation_status or "imported_untrusted"
        prepared.append(d)

    if strict and errors:
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

    op = operation_id or (
        "imp:" + hashlib.sha256(
            json.dumps([d.harness_id for d in prepared], sort_keys=True).encode()
        ).hexdigest()[:24]
    )

    try:
        with _registry_write_lock():
            base = _reload_committed_locked()
            if op in _APPLIED_OPS or op in _read_disk_applied_ops():
                _emit_registry_event("mutation_deduplicated", {"operation_id": op[:40]})
                return {
                    "added": 0,
                    "total": len(_REG),
                    "deduplicated": True,
                    "revision": _LOADED_REVISION,
                    "rejected": 0,
                    "errors": [],
                }
            snapshot = dict(_REG)
            added = 0
            under_errors: list[str] = []
            for d in prepared:
                if d.harness_id in _pilot_ids():
                    under_errors.append("PILOT_ID_COLLISION")
                    continue
                if d.harness_id in _REG:
                    under_errors.append("DUPLICATE_OR_EXISTING")
                    continue
                _REG[d.harness_id] = d
                added += 1
            if strict and under_errors:
                _REG.clear()
                _REG.update(snapshot)
                _emit_registry_event("import_rejected", {
                    "rejected": len(under_errors),
                })
                return {
                    "added": 0,
                    "total": len(_REG),
                    "error": "IMPORT_VALIDATION_FAILED",
                    "rejected": len(under_errors),
                    "errors": under_errors[:_MAX_ERRORS_REPORTED],
                    "revision": _LOADED_REVISION,
                }
            if added:
                try:
                    _persist_locked(expected_revision=base, operation_id=op)
                except Exception as e:
                    _REG.clear()
                    _REG.update(snapshot)
                    # re-sync from disk if needed
                    try:
                        _reload_committed_locked()
                    except Exception:
                        pass
                    return {
                        "added": 0,
                        "total": len(_REG),
                        "error": f"PERSIST_FAILED:{type(e).__name__}",
                        "rejected": 0,
                        "revision": _LOADED_REVISION,
                    }
            return {
                "added": added,
                "total": len(_REG),
                "rejected": len(under_errors),
                "errors": under_errors[:_MAX_ERRORS_REPORTED] if under_errors else [],
                "revision": _LOADED_REVISION,
            }
    except RegistryBusy:
        return {
            "added": 0,
            "total": len(_REG),
            "error": "LOCK_TIMEOUT",
            "rejected": 0,
        }
    except RegistryConflict as e:
        return {
            "added": 0,
            "total": len(_REG),
            "error": "CONFLICT",
            "detail": _truncate_err(str(e)),
            "rejected": 0,
        }


def persist() -> str:
    """Atomically write current in-memory registry to STORE under the write lock.

    CAS: if durable revision advanced since last load, reloads and raises
    RegistryConflict (never overwrites with stale memory). Prefer register() /
    import_records() for multi-writer-safe mutations.
    """
    _bootstrap()
    with _registry_write_lock():
        disk_rev = _read_disk_revision()
        if disk_rev != _LOADED_REVISION:
            _emit_registry_event("revision_conflict", {
                "expected": _LOADED_REVISION, "disk": disk_rev,
            })
            _reload_committed_locked()
            raise RegistryConflict(
                f"STALE_REVISION:expected={_LOADED_REVISION}:disk={disk_rev}"
            )
        return _persist_locked(expected_revision=disk_rev)


def reset_for_tests(*, store: Path | None = None) -> None:
    """Clear in-memory registry (and optionally retarget STORE). Tests only."""
    global STORE, _LAST_LOAD, _PILOT_IDS_CACHE, _LOADED_REVISION, _APPLIED_OPS
    _REG.clear()
    _LAST_LOAD = {
        "status": "not_attempted",
        "loaded": 0,
        "merged": 0,
        "skipped": 0,
        "errors": [],
        "policy": "envelope_fail_closed_entry_skip",
    }
    _LOADED_REVISION = 0
    _APPLIED_OPS = []
    _PILOT_IDS_CACHE = None
    _HEALTH_DIAG.clear()
    _HEALTH_DIAG.update({
        "last_load_time": None,
        "last_successful_write": None,
        "last_validation": None,
        "last_atomic_write": None,
        "last_conflict": None,
        "last_recovery": None,
        "failed_validations": 0,
        "last_validation_status": None,
        "warnings": [],
    })
    if store is not None:
        STORE = Path(store)
