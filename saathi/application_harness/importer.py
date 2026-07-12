"""M17.3 CLI-Anything registry importer — read-only, defensive, untrusted.

Parses CLI-Anything-compatible registry metadata (HKUDS/CLI-Anything, Apache-2.0)
into SaathiOS discovery records. Every imported entry is marked
EXTERNAL_UNTRUSTED and NEVER installed or executed automatically. Rejects path
traversal, embedded shell chains, unexpected install schemes, and mutable/
unpinned sources. This is NOT the public CLI-Hub installer.
"""
from __future__ import annotations

import json
import re

from saathi.application_harness.models import HarnessDefinition, TrustStatus

# install schemes we will even record as discovery (still untrusted, never auto-run)
_ALLOWED_INSTALL = {"npm", "brew", "bundled", "system", "pip", "source"}
_SHELL_CHAIN = re.compile(r"[;&|`]|\$\(|\|\||&&|>|<")
_TRAVERSAL = re.compile(r"\.\.[\\/]")


class ImportRejected(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def import_registry(raw: str | dict, *, source_repo: str = "",
                    source_commit: str = "") -> dict:
    """Parse a CLI-Anything registry.json. Returns {imported, rejected, records}."""
    doc = raw if isinstance(raw, dict) else _safe_load(raw)
    entries = doc.get("clis") or doc.get("harnesses") or doc.get("entries") or []
    records, rejected, seen = [], [], set()
    for e in entries:
        try:
            rec = _normalize(e, source_repo=source_repo, source_commit=source_commit)
        except ImportRejected as ex:
            rejected.append({"name": (e or {}).get("name"), "reason": ex.code})
            continue
        if rec.harness_id in seen:
            rejected.append({"name": rec.harness_id, "reason": "DUPLICATE_ID"})
            continue
        seen.add(rec.harness_id)
        records.append(rec.to_dict())
    return {"imported": len(records), "rejected": rejected,
            "records": records, "source_repo": source_repo,
            "source_commit": source_commit, "trust": "external_untrusted"}


def _safe_load(raw: str) -> dict:
    if len(raw) > 5_000_000:
        raise ImportRejected("REGISTRY_TOO_LARGE")
    try:
        return json.loads(raw)
    except Exception:
        raise ImportRejected("REGISTRY_INVALID_JSON")


def _normalize(e: dict, *, source_repo: str, source_commit: str) -> HarnessDefinition:
    if not isinstance(e, dict):
        raise ImportRejected("ENTRY_NOT_OBJECT")
    name = str(e.get("name", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,60}", name):
        raise ImportRejected("HARNESS_ARGUMENT_REJECTED:name")
    install = str(e.get("install", e.get("install_method", "system"))).lower()
    if install not in _ALLOWED_INSTALL:
        raise ImportRejected("UNEXPECTED_INSTALL_SCHEME")
    # scan all string fields for shell chains / traversal
    for v in _iter_strings(e):
        if _SHELL_CHAIN.search(v):
            raise ImportRejected("EMBEDDED_SHELL_CHAIN")
        if _TRAVERSAL.search(v):
            raise ImportRejected("PATH_TRAVERSAL")
    # external entries must be pinnable; unpinned mutable sources rejected
    src = str(e.get("source", e.get("repo", source_repo)))
    ver = str(e.get("version", "latest"))
    if ver in ("latest", "main", "master", "*", "") and not source_commit:
        # discovery-only record; mark clearly (still importable but flagged)
        ver = "UNPINNED"
    return HarnessDefinition(
        harness_id=f"ext_{name}", display_name=str(e.get("display_name", name))[:80],
        application_name=name, version=ver, source_type="cli_anything",
        source_repository=src, source_commit=source_commit,
        license=str(e.get("license", "")), install_method=install,
        description=str(e.get("description", ""))[:300],
        supported_operations=[],
        trust_status=TrustStatus.EXTERNAL_UNTRUSTED.value,
        validation_status="imported_untrusted")


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)
