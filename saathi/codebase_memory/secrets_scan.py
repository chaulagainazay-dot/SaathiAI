"""Secret and prohibited-content scanning before index persistence.

Uses high-confidence patterns only for source/docs. Configuration files get
stricter assignment checks. Never stores secret values in reasons or logs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from saathi.mcp_governance.redaction import redact_text

# High-confidence value shapes (never log the match group)
_HIGH_CONFIDENCE = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private_key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{24,}\b"), "api_key_shape"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "github_token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "slack_token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_key_id"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{32,}\b", re.I), "bearer_token"),
    (re.compile(
        r"(?i)(?:export\s+)?(?:AWS_SECRET_ACCESS_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|"
        r"GEMINI_API_KEY|GITHUB_TOKEN|DATABASE_URL)\s*=\s*\S{8,}"
    ), "env_secret_assignment"),
    (re.compile(
        r"(?i)(?:password|passwd|secret_key|api_key|access_token|refresh_token)"
        r"\s*[:=]\s*['\"][^'\"]{12,}['\"]"
    ), "quoted_secret_assignment"),
    (re.compile(
        r"(?i)(?:password|api_key|secret)\s*[:=]\s*[A-Za-z0-9/+=]{16,}\s*$", re.M
    ), "bare_secret_assignment"),
]


@dataclass
class ScanResult:
    allowed: bool
    reason: str = ""
    redacted_preview: str = ""


def scan_content(text: str, *, path: str = "", file_class: str = "") -> ScanResult:
    """Fail closed only on high-confidence secret material."""
    if text is None:
        return ScanResult(allowed=False, reason="empty_or_null")
    if "\x00" in text[:8192]:
        return ScanResult(allowed=False, reason="binary_null")

    sample = text if len(text) <= 250_000 else text[:250_000]
    for pat, label in _HIGH_CONFIDENCE:
        if pat.search(sample):
            return ScanResult(
                allowed=False,
                reason=f"secret_pattern:{label}",
                redacted_preview=redact_text(sample[:80], max_len=80),
            )

    # Config / env-like paths: extra caution on private key material
    low = (path or "").lower()
    if low.endswith((".pem", ".key", ".p12", ".pfx")) or low.endswith("id_rsa"):
        return ScanResult(allowed=False, reason="secret_path_extension")

    return ScanResult(allowed=True)


def safe_exclusion_log(reason: str, path: str) -> dict:
    return {
        "path": path[:400],
        "reason": reason[:120],
        "secret_value_recorded": False,
    }
