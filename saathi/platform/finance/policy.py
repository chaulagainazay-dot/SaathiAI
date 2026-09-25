"""Financial Browser security policy — the freezable security contract (pure, no I/O).

Structural enforcement of: owner/agent actor separation, interaction modes, prohibited
agent actions, credential-field redaction, per-provider domain/region policy, and the
provider capability matrix. No network, no secrets, no browser here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Provider(str, Enum):
    NEPSE = "NEPSE"
    TMS = "TMS"
    BINANCE = "BINANCE"
    PORTFOLIO_TRACKER = "PORTFOLIO_TRACKER"
    MEROSHARE = "MEROSHARE"
    COINMARKETCAP = "COINMARKETCAP"


class Actor(str, Enum):
    OWNER_INPUT = "OWNER_INPUT"
    AGENT_INPUT = "AGENT_INPUT"


class InteractionMode(str, Enum):
    OWNER_CONTROL = "OWNER_CONTROL"                    # owner interacts normally
    AGENT_READ_ONLY = "AGENT_READ_ONLY"               # agent may observe approved data
    OWNER_APPROVAL_REQUIRED = "OWNER_APPROVAL_REQUIRED"  # reserved; separately certified later
    BLOCKED = "BLOCKED"                                # agent cannot interact


class FieldClass(str, Enum):
    OWNER_PRIVATE_INPUT = "OWNER_PRIVATE_INPUT"        # password/OTP/2FA/secret — never observed
    SENSITIVE_READABLE = "SENSITIVE_READABLE"          # balances/account# — read w/ redaction rules
    PUBLIC_READABLE = "PUBLIC_READABLE"


class ProviderCapability(str, Enum):
    PUBLIC_MARKET_DATA = "PUBLIC_MARKET_DATA"
    READ_ONLY_API = "READ_ONLY_API"
    READ_ONLY_MCP = "READ_ONLY_MCP"
    OWNER_BROWSER_SESSION = "OWNER_BROWSER_SESSION"
    AGENT_READ_ALLOWED = "AGENT_READ_ALLOWED"
    OWNER_ONLY_INTERACTION = "OWNER_ONLY_INTERACTION"
    AGENT_ACTION_REQUIRES_APPROVAL = "AGENT_ACTION_REQUIRES_APPROVAL"
    PROHIBITED_AGENT_ACTION = "PROHIBITED_AGENT_ACTION"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class EmbedSupport(str, Enum):
    EMBED_SUPPORTED = "EMBED_SUPPORTED"
    EMBED_BLOCKED = "EMBED_BLOCKED"
    EXTERNAL_BROWSER_REQUIRED = "EXTERNAL_BROWSER_REQUIRED"
    NATIVE_WEBVIEW_REQUIRED = "NATIVE_WEBVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


# Every agent-originated account action is prohibited (Phase 8) — structural, not advisory.
PROHIBITED_AGENT_ACTIONS = frozenset({
    "BUY", "SELL", "PLACE_ORDER", "MODIFY_ORDER", "CANCEL_ORDER", "WITHDRAW", "DEPOSIT",
    "TRANSFER", "SEND_CRYPTO", "SWAP", "CONVERT", "BORROW", "REPAY", "ENABLE_MARGIN",
    "ENABLE_FUTURES", "CHANGE_LEVERAGE", "CREATE_API_KEY", "DELETE_API_KEY",
    "CHANGE_PASSWORD", "CHANGE_2FA", "ADD_BANK_ACCOUNT", "ADD_WITHDRAWAL_ADDRESS",
    "WHITELIST_ADDRESS",
})

# Read capabilities an agent MAY perform when a provider region is AGENT_READ_ONLY.
ALLOWED_AGENT_READS = frozenset({
    "READ_PORTFOLIO", "READ_HOLDINGS", "READ_BALANCE", "READ_PNL", "READ_QUOTE",
    "READ_HISTORY", "READ_FUNDAMENTALS", "READ_DIVIDENDS", "OBSERVE_PUBLIC_PAGE",
})

# Authentication challenges are owner-only (Phase 4).
OWNER_AUTH_CHALLENGES = frozenset({
    "CAPTCHA", "OTP", "TWO_FACTOR", "PASSKEY", "DEVICE_CONFIRMATION", "SECURITY_QUESTION",
})

# Credential-ish field detection → OWNER_PRIVATE_INPUT (never observed/logged/screenshotted).
_PRIVATE_FIELD_RE = re.compile(
    r"pass(word|code)|otp|2fa|mfa|totp|cvv|pin\b|secret|api[_-]?key|private[_-]?key|"
    r"seed|mnemonic|recovery|security[_-]?(code|answer|question)|token", re.I)
_SENSITIVE_FIELD_RE = re.compile(
    r"balance|account[_-]?(no|number|id)|iban|swift|wallet|address|email|phone|pan\b", re.I)

# Secret patterns to redact from any string that could reach a log/model/event.
_SECRET_PATTERNS = [
    # header/kv secrets: consume the whole value to end-of-line
    re.compile(r"(?im)\b(authorization|x-mcp-key|x-saathi-token|api[_-]?key|secret|"
               r"password|passcode|token|cookie)\b\s*[:=]\s*.+$"),
    re.compile(r"(?i)\bBearer\s+\S+"),
    re.compile(r"\b[A-Za-z0-9._-]{20,}\b"),        # long opaque tokens
    re.compile(r"\b[0-9]{6}\b"),                    # OTP-looking codes
]


@dataclass(frozen=True)
class FinancialBrowserPolicy:
    provider: Provider
    allowed_domains: tuple[str, ...]
    allowed_paths: tuple[str, ...] = ("/",)          # path prefixes the owner may open
    readable_regions: tuple[str, ...] = ()           # agent AGENT_READ_ONLY regions
    sensitive_regions: tuple[str, ...] = ()          # readable w/ redaction
    owner_only_regions: tuple[str, ...] = ()         # login/settings/order forms
    prohibited_agent_actions: frozenset = PROHIBITED_AGENT_ACTIONS
    allowed_downloads: bool = False
    allowed_uploads: bool = False
    navigation_policy: str = "ALLOWLIST_ONLY"        # no arbitrary browsing
    session_policy: str = "OWNER_AUTHENTICATED_ONLY"
    default_interaction_mode: InteractionMode = InteractionMode.OWNER_CONTROL

    def domain_allowed(self, host: str) -> bool:
        h = (host or "").lower()
        return any(h == d or h.endswith("." + d) for d in self.allowed_domains)


# ── per-provider policies (evidence-based; UNKNOWN where unproven) ───────────────
POLICIES: dict[Provider, FinancialBrowserPolicy] = {
    Provider.NEPSE: FinancialBrowserPolicy(
        provider=Provider.NEPSE, allowed_domains=("nepalstock.com",),
        allowed_paths=("/", "/today-price", "/live-market"),
        readable_regions=("index", "today-price-table", "market-summary"),
        owner_only_regions=(),                       # public site; no owner account here
        default_interaction_mode=InteractionMode.AGENT_READ_ONLY),
    Provider.PORTFOLIO_TRACKER: FinancialBrowserPolicy(
        provider=Provider.PORTFOLIO_TRACKER,
        allowed_domains=("nepseportfoliotracker.app", "api.nepseportfoliotracker.app"),
        readable_regions=("history", "fundamentals", "dividends", "sectors"),
        owner_only_regions=("account", "login", "app"),   # portfolio/account behind login
        default_interaction_mode=InteractionMode.AGENT_READ_ONLY),
    Provider.BINANCE: FinancialBrowserPolicy(
        provider=Provider.BINANCE, allowed_domains=("binance.com", "api.binance.com"),
        allowed_paths=("/",),
        readable_regions=(),                          # account read = future read-only API only
        owner_only_regions=("login", "account", "wallet", "trade", "withdraw", "settings",
                            "api-management"),
        default_interaction_mode=InteractionMode.OWNER_CONTROL),
    Provider.TMS: FinancialBrowserPolicy(
        provider=Provider.TMS, allowed_domains=("nepsetms.com.np",),
        allowed_paths=("/",),
        readable_regions=(),                          # holdings read UNPROVEN → none yet
        owner_only_regions=("login", "member", "tms", "order", "purchase", "settings"),
        default_interaction_mode=InteractionMode.OWNER_CONTROL),
    Provider.MEROSHARE: FinancialBrowserPolicy(
        provider=Provider.MEROSHARE, allowed_domains=("meroshare.cdsc.com.np", "cdsc.com.np"),
        allowed_paths=("/",),
        readable_regions=(),                          # owner-authenticated demat portfolio
        owner_only_regions=("login", "dashboard", "myshare", "portfolio", "settings", "profile"),
        default_interaction_mode=InteractionMode.OWNER_CONTROL),
    Provider.COINMARKETCAP: FinancialBrowserPolicy(
        provider=Provider.COINMARKETCAP, allowed_domains=("coinmarketcap.com",),
        allowed_paths=("/",),
        readable_regions=(),
        owner_only_regions=("login", "account", "watchlist", "portfolio", "settings"),
        default_interaction_mode=InteractionMode.OWNER_CONTROL),
}


# ── structural enforcement ──────────────────────────────────────────────────────
def is_agent_action_allowed(action: str) -> bool:
    """The ONLY agent actions ever allowed are explicit reads. Everything else is blocked."""
    a = (action or "").upper()
    if a in PROHIBITED_AGENT_ACTIONS:
        return False
    return a in ALLOWED_AGENT_READS


def enforce(actor: Actor, action: str, provider: Provider) -> tuple[bool, str]:
    """Decide whether an interaction may proceed. Owner may do anything the owner does in
    their own browser; the agent may only perform allowed reads and NEVER a prohibited
    action. Returns (allowed, reason/mode)."""
    a = (action or "").upper()
    if actor == Actor.OWNER_INPUT:
        return True, InteractionMode.OWNER_CONTROL.value
    # AGENT_INPUT
    if a in PROHIBITED_AGENT_ACTIONS:
        return False, "AGENT_ACTION_BLOCKED"
    if a in ALLOWED_AGENT_READS:
        return True, InteractionMode.AGENT_READ_ONLY.value
    return False, "AGENT_ACTION_BLOCKED"               # default-deny anything unknown


def classify_field(name: str) -> FieldClass:
    n = name or ""
    if _PRIVATE_FIELD_RE.search(n):
        return FieldClass.OWNER_PRIVATE_INPUT
    if _SENSITIVE_FIELD_RE.search(n):
        return FieldClass.SENSITIVE_READABLE
    return FieldClass.PUBLIC_READABLE


def is_owner_private(name: str) -> bool:
    return classify_field(name) == FieldClass.OWNER_PRIVATE_INPUT


def redact(text) -> str:
    """Redact secret-looking substrings before any string reaches a log/model/event."""
    s = str(text)
    for pat in _SECRET_PATTERNS:
        s = pat.sub("«redacted»", s)
    return s


def is_owner_auth_challenge(kind: str) -> bool:
    return (kind or "").upper() in OWNER_AUTH_CHALLENGES
