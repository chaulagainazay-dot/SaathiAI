"""M17.23 browser domain + risk policy (deterministic, fail-closed).

Does not replace ExecutionGateway approval — only classifies risk and
validates target safety before / alongside gateway dispatch.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse, urljoin

from saathi.execution.toolintent import ApprovalLevel, RiskLevel

# ── schemes ───────────────────────────────────────────────────────────────
ALLOWED_SCHEMES = frozenset({"http", "https"})
DANGEROUS_SCHEMES = frozenset({
    "file", "javascript", "data", "vbscript", "blob", "about",
})

# ── default allowlist (dev / staging / localhost) ─────────────────────────
DEFAULT_ALLOWED_HOST_SUFFIXES = (
    "localhost",
    "127.0.0.1",
    "::1",
    "example.com",
    "example.org",
    "example.net",
    "httpbin.org",
    "saathi.local",
    "staging.saathi.local",
)

# Cloud metadata / private ranges blocked by default
_METADATA_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
})

# ── action families ───────────────────────────────────────────────────────


class BrowserAction(str, Enum):
    NAVIGATE = "navigate"
    OPEN = "open"
    READ = "read"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    CLICK = "click"
    TYPE = "type"
    FILL = "fill"
    SUBMIT = "submit"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    WORKFLOW = "workflow"
    # Prohibited / fail-closed
    EVAL_JS = "eval_js"
    ENTER_CREDENTIALS = "enter_credentials"
    TRADE = "trade"
    PAYMENT = "payment"
    PASSWORD_CHANGE = "password_change"
    MFA_BYPASS = "mfa_bypass"
    CAPTCHA_SOLVE = "captcha_solve"
    ACCOUNT_DELETE = "account_delete"


# Low risk — auto-approve when domain + identity allow
LOW_ACTIONS = frozenset({
    BrowserAction.NAVIGATE, BrowserAction.OPEN, BrowserAction.READ,
    BrowserAction.EXTRACT, BrowserAction.SCREENSHOT,
})

# Medium — may auto under staging; approval otherwise
MEDIUM_ACTIONS = frozenset({
    BrowserAction.CLICK, BrowserAction.TYPE, BrowserAction.FILL,
    BrowserAction.DOWNLOAD, BrowserAction.UPLOAD,
})

# High — always approval required
HIGH_ACTIONS = frozenset({
    BrowserAction.SUBMIT, BrowserAction.WORKFLOW,
    BrowserAction.ENTER_CREDENTIALS,
})

# Always denied in this milestone
PROHIBITED_ACTIONS = frozenset({
    BrowserAction.EVAL_JS, BrowserAction.TRADE, BrowserAction.PAYMENT,
    BrowserAction.PASSWORD_CHANGE, BrowserAction.MFA_BYPASS,
    BrowserAction.CAPTCHA_SOLVE, BrowserAction.ACCOUNT_DELETE,
})

_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(password|passwd|secret|token|otp|ssn|card|cvv|iban|credential|auth)"
)
_INJECTION_MARKERS = (
    "ignore all previous instructions",
    "disregard system prompt",
    "reveal your secrets",
    "bypass safety",
    "you are now jailbroken",
    "execute shell",
    "transfer all funds",
    "disable approval",
)


@dataclass(frozen=True)
class DomainDecision:
    allowed: bool
    reason: str
    origin: str = ""
    host: str = ""
    scheme: str = ""


@dataclass(frozen=True)
class RiskDecision:
    risk: RiskLevel
    approval_level: ApprovalLevel
    require_approval: bool
    category: str  # low | medium | high | prohibited
    reason: str


def parse_action(action: str | BrowserAction) -> BrowserAction:
    if isinstance(action, BrowserAction):
        return action
    a = str(action).strip().lower().replace("-", "_")
    aliases = {
        "goto": BrowserAction.NAVIGATE,
        "navigate": BrowserAction.NAVIGATE,
        "open": BrowserAction.OPEN,
        "read": BrowserAction.READ,
        "read_page": BrowserAction.READ,
        "extract": BrowserAction.EXTRACT,
        "screenshot": BrowserAction.SCREENSHOT,
        "click": BrowserAction.CLICK,
        "type": BrowserAction.TYPE,
        "fill": BrowserAction.FILL,
        "submit": BrowserAction.SUBMIT,
        "download": BrowserAction.DOWNLOAD,
        "upload": BrowserAction.UPLOAD,
        "workflow": BrowserAction.WORKFLOW,
        "eval": BrowserAction.EVAL_JS,
        "eval_js": BrowserAction.EVAL_JS,
        "enter_credentials": BrowserAction.ENTER_CREDENTIALS,
    }
    if a in aliases:
        return aliases[a]
    try:
        return BrowserAction(a)
    except ValueError:
        raise ValueError(f"unknown browser action: {action}")


def origin_of(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""
    return f"{p.scheme.lower()}://{p.netloc.lower()}"


def _is_ip_blocked(host: str) -> tuple[bool, str]:
    h = host.strip("[]")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False, ""
    if ip.is_loopback:
        return False, ""  # localhost OK
    if ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast:
        return True, "private_or_link_local_ip"
    if str(ip) == "169.254.169.254":
        return True, "cloud_metadata"
    return False, ""


def check_domain(
    url: str,
    *,
    allowed_hosts: tuple[str, ...] | list[str] | None = None,
    allow_private: bool = False,
) -> DomainDecision:
    """Fail-closed domain / scheme policy."""
    if not url or not isinstance(url, str):
        return DomainDecision(False, "empty_url")
    raw = url.strip()
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    if scheme in DANGEROUS_SCHEMES or scheme not in ALLOWED_SCHEMES:
        return DomainDecision(False, f"dangerous_or_unsupported_scheme:{scheme or 'none'}",
                              scheme=scheme)
    host = (p.hostname or "").lower()
    if not host:
        return DomainDecision(False, "missing_host", scheme=scheme)
    if host in _METADATA_HOSTS or host.endswith(".metadata.google.internal"):
        return DomainDecision(False, "cloud_metadata", origin=origin_of(raw),
                              host=host, scheme=scheme)
    blocked, why = _is_ip_blocked(host)
    if blocked and not allow_private:
        return DomainDecision(False, why, origin=origin_of(raw), host=host, scheme=scheme)

    allow = tuple(allowed_hosts) if allowed_hosts is not None else DEFAULT_ALLOWED_HOST_SUFFIXES
    # exact or suffix match
    ok = False
    for a in allow:
        a = a.lower().lstrip(".")
        if host == a or host.endswith("." + a) or (a in ("localhost", "127.0.0.1", "::1") and host == a):
            ok = True
            break
    if not ok:
        return DomainDecision(False, "domain_not_allowlisted",
                              origin=origin_of(raw), host=host, scheme=scheme)
    return DomainDecision(True, "ok", origin=origin_of(raw), host=host, scheme=scheme)


def revalidate_redirect(original_url: str, final_url: str, **kwargs) -> DomainDecision:
    """Redirects revalidate final destination — original allowlist is not enough."""
    d = check_domain(final_url, **kwargs)
    if not d.allowed:
        return DomainDecision(False, f"redirect_denied:{d.reason}",
                              origin=d.origin, host=d.host, scheme=d.scheme)
    # origin change on high-risk paths is caller's concern; always re-check
    return d


def classify_risk(
    action: str | BrowserAction,
    *,
    url: str = "",
    selector: str = "",
    payload: Optional[dict] = None,
    environment: str = "dev",
) -> RiskDecision:
    act = parse_action(action)
    if act in PROHIBITED_ACTIONS:
        return RiskDecision(
            RiskLevel.CRITICAL, ApprovalLevel.L4, True, "prohibited",
            f"prohibited_action:{act.value}",
        )
    payload = payload or {}
    # sensitive field typing elevates
    field_hint = str(payload.get("field") or selector or "")
    if act in (BrowserAction.TYPE, BrowserAction.FILL) and _SENSITIVE_FIELD_RE.search(field_hint):
        return RiskDecision(
            RiskLevel.HIGH, ApprovalLevel.L4, True, "high",
            "sensitive_field_input",
        )
    if act in HIGH_ACTIONS:
        return RiskDecision(
            RiskLevel.HIGH, ApprovalLevel.L4, True, "high",
            f"high_risk_action:{act.value}",
        )
    if act in MEDIUM_ACTIONS:
        # staging/dev may auto-approve medium clicks on allowlisted domains
        if environment in ("dev", "test", "staging") and act in (
            BrowserAction.CLICK, BrowserAction.TYPE, BrowserAction.FILL,
            BrowserAction.DOWNLOAD,
        ):
            return RiskDecision(
                RiskLevel.MEDIUM, ApprovalLevel.L2, False, "medium",
                f"medium_auto_staging:{act.value}",
            )
        return RiskDecision(
            RiskLevel.MEDIUM, ApprovalLevel.L3, True, "medium",
            f"medium_requires_approval:{act.value}",
        )
    # low
    return RiskDecision(
        RiskLevel.LOW, ApprovalLevel.L1, False, "low",
        f"low_auto:{act.value}",
    )


def payload_digest(payload: Any) -> str:
    import json
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def detect_prompt_injection(text: str) -> list[str]:
    """Page content is untrusted data — flag injection patterns (never auto-execute)."""
    if not text:
        return []
    low = text.lower()
    hits = [m for m in _INJECTION_MARKERS if m in low]
    return hits


def sanitize_filename(name: str, *, maxlen: int = 128) -> str:
    base = name.replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^\w.\-]+", "_", base).strip("._") or "download.bin"
    if ".." in base:
        base = base.replace("..", "_")
    return base[:maxlen]


def path_is_inside(path: str, root: str) -> bool:
    from pathlib import Path
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
        return str(p).startswith(str(r) + "/") or p == r
    except Exception:
        return False
