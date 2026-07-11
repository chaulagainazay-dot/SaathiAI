"""Secret scanning — the security floor of the Auto-Repair Loop.

Every repair commit, every generated report, every collected evidence blob is
scanned first. If a secret pattern matches, the commit is aborted and the
incident is marked SECURITY_ERROR. We report the file + line but NEVER the
matched value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# (name, compiled pattern). Patterns are intentionally broad; false positives
# are safer than a leaked credential.
_PATTERNS = [
    ("huggingface_token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("bearer_jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("url_embedded_credential", re.compile(r"https?://[^/\s:@]+:[^/\s@]+@")),
    ("generic_secret_assignment", re.compile(
        r"(?i)(secret|password|passwd|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
]

# Placeholder values that must never count as secrets (used in templates/tests).
_ALLOWLIST = re.compile(
    r"(?i)REPLACE_WITH|YOUR_|xxxxx|example|placeholder|REDACTED|dummy|<[^>]+>|"
    r"\bsk-local\b|\$\{?[A-Z_]+\}?")  # $ENV / ${ENV} shell placeholders are not secrets


@dataclass
class SecretHit:
    rule: str
    line: int
    # A short, non-revealing fingerprint of the match location only.
    excerpt_redacted: str = "***redacted***"


@dataclass
class ScanResult:
    hits: list[SecretHit] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.hits


def scan_text(text: str) -> ScanResult:
    """Scan a blob of text. Returns hits with line numbers, never values."""
    result = ScanResult()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _ALLOWLIST.search(line):
            continue
        for name, pat in _PATTERNS:
            if pat.search(line):
                result.hits.append(SecretHit(rule=name, line=lineno))
    return result


def scan_files(paths: list[str]) -> dict[str, ScanResult]:
    """Scan files by path. Missing/binary files are skipped safely."""
    out: dict[str, ScanResult] = {}
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                res = scan_text(fh.read())
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            continue
        if not res.clean:
            out[p] = res
    return out


def redact(text: str) -> str:
    """Replace any secret-looking substring with a redaction marker.

    Used before storing evidence/logs so raw captures never persist secrets.
    """
    redacted = text
    for _name, pat in _PATTERNS:
        redacted = pat.sub("***redacted***", redacted)
    return redacted
