"""Aggressive secret detection for M226. Reject secret-shaped values fail-closed."""
from __future__ import annotations

import re
from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    PROHIBITED_SECRET_KEYS,
    SECRET_VALUE_PATTERNS,
)

_COMPILED = [re.compile(p) for p in SECRET_VALUE_PATTERNS]


class SecretRejectionError(Exception):
    def __init__(self, code: str, message: str, field: str = ""):
        self.code = code
        self.message = message
        self.field = field
        super().__init__(f"{code}: {message}")


def looks_like_secret(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return False
    if not isinstance(value, str):
        value = str(value)
    s = value.strip()
    if not s or s.upper() in (
        "REDACTED", "PLACEHOLDER", "NONE", "N/A", "UNUSABLE", "SIMULATED",
        "METADATA_ONLY", "REF_ONLY",
    ):
        return False
    for pat in _COMPILED:
        if pat.search(s):
            return True
    return False


def normalize_key(key: str) -> str:
    return str(key).lower().replace("-", "_").replace(" ", "_")


def reject_secrets_in_payload(payload: Any, *, path: str = "root") -> None:
    """Walk payload and fail closed on prohibited keys or secret-shaped values."""
    if payload is None:
        return
    if isinstance(payload, dict):
        for k, v in payload.items():
            nk = normalize_key(k)
            full = f"{path}.{k}"
            if nk in PROHIBITED_SECRET_KEYS:
                if v not in (None, "", False, 0) and not (
                    isinstance(v, str) and v.upper() in (
                        "REDACTED", "PLACEHOLDER", "NONE", "N/A", "UNUSABLE", "SIMULATED",
                    )
                ):
                    raise SecretRejectionError(
                        "SECRET_MATERIAL_REJECTED",
                        f"Prohibited secret field '{k}' at {full}. "
                        "Credential framework accepts metadata/references only.",
                        field=full,
                    )
            if isinstance(v, str) and looks_like_secret(v):
                raise SecretRejectionError(
                    "SECRET_SHAPED_VALUE_REJECTED",
                    f"Secret-shaped value rejected at {full}.",
                    field=full,
                )
            reject_secrets_in_payload(v, path=full)
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            reject_secrets_in_payload(item, path=f"{path}[{i}]")
    elif isinstance(payload, str) and looks_like_secret(payload):
        raise SecretRejectionError(
            "SECRET_SHAPED_VALUE_REJECTED",
            f"Secret-shaped value rejected at {path}.",
            field=path,
        )


def scan_text_for_secrets(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not text:
        return findings
    for pat in _COMPILED:
        m = pat.search(text)
        if m:
            findings.append({"pattern": pat.pattern, "match_preview": m.group(0)[:20] + "..."})
    return findings


__all__ = [
    "SecretRejectionError",
    "looks_like_secret",
    "reject_secrets_in_payload",
    "scan_text_for_secrets",
]
