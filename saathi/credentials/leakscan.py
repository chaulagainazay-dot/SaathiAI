"""M31 — Synthetic secret-leak detector.

A defensive scanner that walks arbitrary Python structures (the kind about to be
written to evidence, events, or logs) and flags anything that looks like secret
material — token shapes, key blocks, bearer headers, PKCE verifiers, auth codes,
or forbidden field *names* carrying non-trivial values.

It is deliberately conservative (prefers false positives) and is used to *guard*
evidence emission: if a leak is detected, the write is refused. Findings never
include the offending value — only a redacted preview and a classification.

The fake provider mints synthetic `atk_`/`rtk_`/`ac_` tokens; those are treated as
real-shaped for scan purposes so the guard is exercised by tests, but the broker's
own metadata (which holds field *names*, not values) scans clean.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from saathi.credentials.models import FORBIDDEN_SECRET_FIELD_NAMES

# Value-shape patterns (classification, compiled regex).
_VALUE_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+")),
    ("pem_private_key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")),
    ("google_oauth_token", re.compile(r"ya29\.[A-Za-z0-9_-]{10,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{12,}")),
    ("bearer_header", re.compile(r"[Bb]earer\s+[A-Za-z0-9._~+/-]{10,}=*")),
    ("sandbox_access_token", re.compile(r"\batk_[0-9a-f]{16,}")),
    ("sandbox_refresh_token", re.compile(r"\brtk_[0-9a-f]{16,}")),
    ("sandbox_auth_code", re.compile(r"\bac_[0-9a-f]{16,}")),
]

# Keys whose *value* (if a non-empty string) is a leak regardless of shape.
_SECRET_VALUE_KEYS = frozenset(FORBIDDEN_SECRET_FIELD_NAMES) | {
    "code_verifier", "pkce_verifier", "state_param", "auth_code",
    "access", "refresh", "secret_value",
}

# Substrings marking a key as secret-bearing.
_SECRET_KEY_SUBSTR = ("secret", "token", "password", "passwd", "cookie", "verifier")

# Metadata keys that legitimately carry boolean/enum markers, not values.
_ALLOWED_MARKER_KEYS = frozenset({
    "contains_secret_values", "has_access_token", "has_refresh_token",
    "privacy_safe", "state_param_present", "pkce_challenge_present",
    "real_credentials_stored", "real_oauth_flows_completed",
})


@dataclass
class LeakFinding:
    path: str
    classification: str
    preview: str  # redacted

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "classification": self.classification, "preview": self.preview}


def _redact(value: str) -> str:
    v = str(value)
    if len(v) <= 6:
        return "***"
    return f"{v[:3]}…{v[-2:]} (len={len(v)})"


def _scan_string(value: str, path: str, out: list[LeakFinding]) -> None:
    for classification, pat in _VALUE_PATTERNS:
        if pat.search(value):
            out.append(LeakFinding(path, classification, _redact(value)))
            return


def scan(obj: Any, *, path: str = "$") -> list[LeakFinding]:
    """Recursively scan a structure. Returns all findings (empty == clean)."""
    out: list[LeakFinding] = []
    _walk(obj, path, out)
    return out


def _walk(obj: Any, path: str, out: list[LeakFinding]) -> None:
    if isinstance(obj, str):
        _scan_string(obj, path, out)
        return
    if isinstance(obj, (bytes, bytearray)):
        try:
            _scan_string(obj.decode("utf-8", "ignore"), path, out)
        except Exception:
            pass
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}"
            lk = str(k).lower()
            if lk in _ALLOWED_MARKER_KEYS:
                continue
            # Key marked secret + non-trivial string value → leak.
            key_is_secret = lk in _SECRET_VALUE_KEYS or any(s in lk for s in _SECRET_KEY_SUBSTR)
            if key_is_secret and isinstance(v, str) and v.strip():
                out.append(LeakFinding(kp, f"secret_field_value:{lk}", _redact(v)))
                continue
            _walk(v, kp, out)
        return
    if isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", out)
        return
    # numbers / bools / None → not scannable


def is_clean(obj: Any) -> bool:
    return not scan(obj)


class LeakDetected(Exception):
    def __init__(self, findings: list[LeakFinding]):
        super().__init__(f"secret_leak_detected:{len(findings)}")
        self.findings = findings


def assert_clean(obj: Any, *, context: str = "") -> None:
    """Raise LeakDetected if any secret-shaped material is present.

    Used to fail-closed before writing evidence/events. Never logs the value.
    """
    findings = scan(obj, path=context or "$")
    if findings:
        raise LeakDetected(findings)
