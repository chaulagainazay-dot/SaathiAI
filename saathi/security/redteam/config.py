"""M15.2 red-team harness configuration + safety guards.

Authorized-testing-only enforcement lives here: targets must be local/staging/
test, production URLs are blocked, cloud sync is OFF by default, secrets are
redacted from every stored artifact, and budgets bound attack count / time /
tokens. The harness is a DEVELOPMENT-SECURITY tool — never on the production
request path.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Pinned external adversarial generator. HackAgent is Apache-2.0. We integrate it
# as an OPTIONAL dev-security dependency, never a production dependency. Record
# the reviewed version here; the wrapper refuses to run an unpinned import.
HACKAGENT_PINNED_VERSION = "0.3.0"  # reviewed; install via optional extra only

# Modes. local is the default; cloud sync is never enabled implicitly.
ALLOWED_MODES = {"local", "staging", "test"}
DEFAULT_MODE = "local"

# Hosts that are always allowed as targets (in-process + loopback only).
_ALLOWED_HOST_RE = re.compile(r"^(inproc|localhost|127\.0\.0\.1|::1|0\.0\.0\.0)$")
# Anything that looks like a public/production endpoint is refused.
_PROD_MARKERS = ("http://", "https://")
_PROD_DENY_RE = re.compile(r"(?i)\b(prod|production|api\.|www\.|\.com|\.io|\.ai|\.net|\.org)\b")

# secret-ish tokens redacted from every stored artifact
_SECRET_RE = re.compile(
    r"(?i)(token|secret|api[_-]?key|password|passwd|bearer|cookie|authorization|"
    r"client[_-]?secret|private[_-]?key)\s*[=:]\s*(?:bearer\s+)?\S+")
# bare "Bearer <token>" anywhere (e.g. inside an Authorization header value)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+\S+")
# provider token shapes (sk-, ghp_, gho_, xoxb-, AKIA…) even without a label
_TOKEN_SHAPE_RE = re.compile(
    r"\b(sk-[A-Za-z0-9]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|"
    r"AKIA[0-9A-Z]{12,})\b")
_ENVVAR_VALUE_RE = re.compile(r"\b([A-Z][A-Z0-9_]{6,})=([^\s]{6,})")


class TargetNotAuthorized(Exception):
    pass


@dataclass
class Budget:
    max_attacks: int = 500
    max_concurrency: int = 1        # in-process deterministic runner is serial
    max_tokens: int = 0             # 0 = no LLM calls (deterministic-only default)
    max_runtime_sec: int = 120
    max_generator_calls: int = 0
    max_judge_calls: int = 0
    max_target_requests: int = 2000


@dataclass
class RedTeamConfig:
    mode: str = DEFAULT_MODE
    cloud_sync: bool = False         # NEVER default-on
    target: str = "inproc"           # in-process SaathiOS test target
    isolated_user: str = "redteam-tester"
    isolated_project: str = "redteam-project"
    isolated_namespace: str = "redteam"
    budget: Budget = field(default_factory=Budget)
    hackagent_enabled: bool = False  # off unless explicitly + installed + pinned

    def validate(self) -> None:
        if self.mode not in ALLOWED_MODES:
            raise TargetNotAuthorized(f"mode {self.mode!r} not in {ALLOWED_MODES}")
        if self.cloud_sync:
            raise TargetNotAuthorized("cloud sync must not be enabled in this harness")
        assert_target_authorized(self.target)


def assert_target_authorized(target: str) -> None:
    """Block production / third-party targets. Only in-process or loopback."""
    t = (target or "").strip()
    if t == "inproc":
        return
    # extract host
    host = t
    for p in _PROD_MARKERS:
        if host.startswith(p):
            host = host[len(p):]
    host = host.split("/")[0].split(":")[0]
    if _PROD_DENY_RE.search(t):
        raise TargetNotAuthorized(f"target {t!r} looks like a production/public endpoint")
    if not _ALLOWED_HOST_RE.match(host):
        raise TargetNotAuthorized(f"target host {host!r} not authorized (local/staging only)")


def redact(text: str) -> str:
    """Redact secret-shaped substrings from any artifact before storage/report."""
    if not isinstance(text, str):
        text = str(text)
    text = _SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _ENVVAR_VALUE_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return text


def redact_obj(obj):
    """Recursively redact strings inside a JSON-able structure."""
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


def env_mode() -> str:
    return os.getenv("SAATHI_REDTEAM_MODE", DEFAULT_MODE)
