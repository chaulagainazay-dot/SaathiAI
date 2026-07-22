"""M33 — External fixture capture, sanitization, and leak scanning.

Any external response fixture committed to the repository must be small,
sanitized, deterministic, and free of secrets / cookies / tokens / personal data /
unstable ids. Fixtures are stored as canonical normalized bodies with recorded
provenance. Loading a fixture re-runs the M31 leak scanner and fails closed if
anything secret-shaped is present. Raw provider responses are never committed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saathi.connectors.providers.normalization import _strip_sensitive
from saathi.credentials.leakscan import LeakDetected, assert_clean, scan

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"

# Unstable / unnecessary keys stripped from any committed fixture body.
UNSTABLE_KEYS = frozenset({
    "request_id", "x-request-id", "x-github-request-id", "timestamp", "date",
    "etag", "last-modified", "trace_id", "correlation_id", "server_time",
})

MAX_FIXTURE_BYTES = 64 * 1024


class FixtureError(ValueError):
    pass


def fixture_path(provider_id: str, name: str) -> Path:
    fn = name if name.endswith(".json") else f"{name}.json"
    return FIXTURE_ROOT / provider_id / fn


def sanitize_fixture_body(body: Any) -> Any:
    """Strip sensitive + unstable material from a fixture body (deterministic)."""
    cleaned = _strip_sensitive(body)
    if isinstance(cleaned, dict):
        return {k: v for k, v in cleaned.items() if str(k).lower() not in UNSTABLE_KEYS}
    return cleaned


def scan_fixture(obj: Any) -> list[dict[str, Any]]:
    return [f.to_dict() for f in scan(obj)]


def assert_fixture_clean(obj: Any, *, context: str = "m33.fixture") -> None:
    """Fail closed if a fixture would leak a secret."""
    assert_clean(obj, context=context)


def load_fixture(provider_id: str, name: str = "get_meta.success") -> dict[str, Any]:
    """Load, size-check, leak-scan, and return a committed fixture. Fails closed."""
    p = fixture_path(provider_id, name)
    if not p.is_file():
        raise FixtureError(f"fixture_missing:{provider_id}/{name}")
    raw = p.read_bytes()
    if len(raw) > MAX_FIXTURE_BYTES:
        raise FixtureError(f"fixture_too_large:{len(raw)}")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise FixtureError(f"fixture_unparseable:{type(e).__name__}")
    # provenance is mandatory
    for req in ("provider_id", "operation", "capture_method", "body"):
        if req not in doc:
            raise FixtureError(f"fixture_missing_provenance:{req}")
    assert_fixture_clean(doc, context=f"m33.fixture:{provider_id}/{name}")
    return doc


def fixture_body(provider_id: str, name: str = "get_meta.success") -> dict[str, Any]:
    return load_fixture(provider_id, name)["body"]


def fixture_body_bytes(provider_id: str, name: str = "get_meta.success") -> bytes:
    """Deterministic canonical JSON encoding of a fixture body (for injected transport)."""
    body = fixture_body(provider_id, name)
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fixture_provenance(provider_id: str, name: str = "get_meta.success") -> dict[str, Any]:
    doc = load_fixture(provider_id, name)
    return {
        "provider_id": doc.get("provider_id"),
        "operation": doc.get("operation"),
        "capture_method": doc.get("capture_method"),
        "official_documentation_reference": doc.get("official_documentation_reference", ""),
        "privacy_safe": True,
    }
