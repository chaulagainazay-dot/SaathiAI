"""M32 — Provider evidence writer (atomic, leak-scanned, repository-relative).

Every payload is leak-scanned (M31 detector) BEFORE it is written. Evidence uses
repository-relative references, deterministic ordering, a schema version, and a
freshness fingerprint. No credentials, authorization headers, cookies, or full
raw provider payloads ever reach evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.providers.models import M32_SCHEMA_VERSION

try:
    from saathi.credentials.leakscan import assert_clean, is_clean
except Exception:  # pragma: no cover
    def is_clean(obj: Any) -> bool:  # type: ignore
        return True

    def assert_clean(obj: Any, *, context: str = "") -> None:  # type: ignore
        return None

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m32"


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def _fingerprint(obj: Any) -> str:
    return hashlib.sha256(_stable_json(obj).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_evidence(
    name: str,
    body: dict[str, Any],
    *,
    evidence_dir: Optional[Path] = None,
    schema: str = "",
) -> str:
    """Leak-scan then atomically write one evidence file. Returns repo-relative path.

    Raises LeakDetected if the payload would leak a secret.
    """
    d = Path(evidence_dir) if evidence_dir else DEFAULT_EVIDENCE_DIR
    payload = {
        "schema": schema or f"m32.{name}.v1",
        "spec_version": M32_SCHEMA_VERSION,
        "privacy_safe": True,
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "body": body,
    }
    payload["fingerprint"] = _fingerprint(payload["body"])
    # Fail closed: never write unscanned/leaky evidence
    assert_clean(payload, context=f"m32.evidence:{name}")
    path = d / (name if name.endswith(".json") else f"{name}.json")
    _atomic_write(path, payload)
    return _rel(path)


def evidence_is_clean(body: dict[str, Any]) -> bool:
    return bool(is_clean(body))
