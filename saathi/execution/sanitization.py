"""Sanitising execution output before it leaves the gateway.

Tool and connector output is untrusted data. It is shaped by whatever the tool
talked to, so it can carry a credential the caller never intended to expose --
an echoed request header, an error that quotes a connection string, a provider
response that includes the key it was called with.

`ExecutionGateway.sanitize_result` carried `# TODO: Implement sanitization` and
stripped nothing. It did not leak, because it also dropped the payload entirely
and returned a status-only object; but `SaathiExecutionSystem.execute_intent`
returned the *raw* result to its caller and the sanitised one went only to
evidence. So the boundary existed on paper and the payload went round it.

Scope is deliberately narrow. This protects the credential boundary; it is not a
data-loss-prevention system and does not judge business content. A sanitiser
that redacts everything is useless in a different way from one that redacts
nothing -- both destroy the tool result's purpose -- so ordinary values, ids and
prose must survive untouched, and that is tested as hard as the redaction is.

The detection itself is not reinvented here. `saathi.tool_runtime.secrets` is the
repository's existing key-aware scanner, already used on the tool-runtime path;
a second opinion about what a secret looks like is a second thing to keep in
sync, and the one that drifts is the one that misses.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from saathi.tool_runtime.secrets import REDACTED, is_secret_key, looks_like_secret_value

#: How much of a free-text field is scanned. Unbounded scanning of an arbitrarily
#: large payload is its own availability problem, and the patterns below are all
#: anchored to short tokens, so a cap costs little detection. Text beyond it is
#: truncated rather than passed through unscanned -- unscanned output must never
#: reach the caller just because it was long.
MAX_TEXT_CHARS = 200_000

#: Categories reported in provenance. Names only; never a matched value.
CAT_SECRET_KEY = "secret_key"
CAT_SECRET_VALUE = "secret_value"
CAT_INLINE_TEXT = "inline_text"
CAT_TRUNCATED = "truncated"
CAT_UNINSPECTABLE = "uninspectable"

#: Credential shapes that appear *inside* free text, where there is no key to
#: judge by. Deliberately few and high-confidence: each one is a token format
#: with a distinctive prefix or structure, so ordinary identifiers, UUIDs, hashes
#: and hex strings do not match. Broadening this is how a sanitiser starts
#: eating real results.
_INLINE_SECRET_RE = re.compile(
    r"""(
        sk-[A-Za-z0-9]{16,}                    # OpenAI-style
      | ghp_[A-Za-z0-9]{20,}                   # GitHub personal token
      | gho_[A-Za-z0-9]{20,}
      | xox[baprs]-[A-Za-z0-9-]{10,}           # Slack
      | AKIA[0-9A-Z]{16}                       # AWS access key id
      | -----BEGIN[ A-Z]*PRIVATE\ KEY-----     # PEM private key
      | eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}  # JWT
    )""",
    re.VERBOSE,
)

#: `Authorization: Bearer <token>` and `Cookie: a=b` style lines, plus
#: `password=...` / `api_key=...` assignments, which is how credentials most
#: often appear in an error message or a captured request.
_INLINE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(authorization|cookie|set-cookie|password|passwd|api[_-]?key|access[_-]?token
      |refresh[_-]?token|client[_-]?secret|secret|token)
    \s*[:=]\s*
    (?:bearer\s+)?
    (?P<value>[^\s,;'"]{6,})
    """,
)


@dataclass
class SanitizationReport:
    """What was removed, in terms safe to store and show.

    Counts and category names only. A report that named the field it redacted
    would be a map to the secret, and one that quoted the value would be the
    leak it was preventing.
    """

    redaction_count: int = 0
    categories: set[str] = field(default_factory=set)
    #: True when sanitisation itself failed. The payload is dropped in that case
    #: -- see `sanitize`.
    failed: bool = False

    @property
    def clean(self) -> bool:
        """Whether the output can be relied on as secret-free.

        False when sanitisation failed, because "we could not check" is not
        "there was nothing to find".
        """
        return not self.failed

    def note(self) -> str:
        """One deterministic line for provenance. No values, ever."""
        if self.failed:
            return "sanitization_failed: payload withheld"
        if not self.redaction_count:
            return "sanitized: 0 redactions"
        cats = ",".join(sorted(self.categories))
        return f"sanitized: {self.redaction_count} redactions [{cats}]"

    def to_dict(self) -> dict:
        return {
            "sanitized": not self.failed,
            "redaction_count": self.redaction_count,
            "redaction_categories": sorted(self.categories),
        }


def _redact_text(text: str, report: SanitizationReport) -> str:
    """Remove credential-shaped substrings from free text.

    Keeps the surrounding message: an error that says *what* failed is worth
    far more than one reduced to `[REDACTED]`, and diagnostic value is the whole
    reason error strings are returned at all.
    """
    if len(text) > MAX_TEXT_CHARS:
        report.redaction_count += 1
        report.categories.add(CAT_TRUNCATED)
        text = text[:MAX_TEXT_CHARS] + "…[truncated]"

    def _sub_token(match: re.Match) -> str:
        report.redaction_count += 1
        report.categories.add(CAT_INLINE_TEXT)
        return REDACTED

    text = _INLINE_SECRET_RE.sub(_sub_token, text)

    def _sub_assignment(match: re.Match) -> str:
        report.redaction_count += 1
        report.categories.add(CAT_INLINE_TEXT)
        # Keep the field name -- it says which credential was involved without
        # disclosing it, which is what an operator reading the log needs.
        return match.group(0).replace(match.group("value"), REDACTED)

    return _INLINE_ASSIGNMENT_RE.sub(_sub_assignment, text)


def _walk(obj: Any, report: SanitizationReport, depth: int = 0) -> Any:
    """Structured redaction first, falling back to text scanning for strings.

    Key-aware, because a key called `password` is decisive in a way its value's
    shape is not: a short or oddly-formatted password is still a password.
    """
    if depth > 40:
        # Depth is bounded rather than trusted. A structure this deep is either
        # hostile or a cycle, and either way it is not returned unscanned.
        report.redaction_count += 1
        report.categories.add(CAT_UNINSPECTABLE)
        return REDACTED

    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if is_secret_key(str(key)):
                report.redaction_count += 1
                report.categories.add(CAT_SECRET_KEY)
                out[key] = REDACTED
            elif looks_like_secret_value(value):
                report.redaction_count += 1
                report.categories.add(CAT_SECRET_VALUE)
                out[key] = REDACTED
            else:
                out[key] = _walk(value, report, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        walked = [_walk(v, report, depth + 1) for v in obj]
        return type(obj)(walked) if isinstance(obj, tuple) else walked
    if isinstance(obj, str):
        return _redact_text(obj, report)
    if isinstance(obj, (bytes, bytearray)):
        # Bytes are not inspected. Decoding arbitrary binary to hunt for tokens
        # is expensive and unreliable, and a blob that might carry a credential
        # is not returned on the chance that it does not.
        report.redaction_count += 1
        report.categories.add(CAT_UNINSPECTABLE)
        return f"<{len(obj)} bytes withheld>"
    return obj


def sanitize(payload: Any) -> tuple[Any, SanitizationReport]:
    """Return a sanitised deep copy of `payload`, and what was done to it.

    The input is never mutated: callers keep raw output for their own bounded
    purposes, and a sanitiser that edited it in place would silently change what
    they already hold.

    Fails closed. If sanitisation raises for any reason the payload is dropped
    and the report says so -- there is no branch that returns the original
    because checking it did not work, which is the one shortcut that would make
    every other guarantee here conditional.
    """
    report = SanitizationReport()
    try:
        return _walk(copy.deepcopy(payload), report), report
    except Exception:
        report.failed = True
        report.redaction_count += 1
        report.categories.add(CAT_UNINSPECTABLE)
        return None, report
