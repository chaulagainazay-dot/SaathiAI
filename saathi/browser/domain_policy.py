"""M17.26 — Environment-specific fail-closed domain policy.

Production is deny-by-default. Domain checks use canonical URL parsing and
hostname normalization — never substring matching.

Decisions about actor authorization, approval, Trading Guardian, and retries
remain above this layer. This module only answers: is this URL/host allowed
for the given environment and optional allowlist?
"""
from __future__ import annotations

import ipaddress
import os
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional
from urllib.parse import urlparse, urlunparse


class BrowserEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


# Aliases → canonical environment
_ENV_ALIASES = {
    "dev": BrowserEnvironment.DEVELOPMENT,
    "development": BrowserEnvironment.DEVELOPMENT,
    "local": BrowserEnvironment.DEVELOPMENT,
    "test": BrowserEnvironment.TEST,
    "testing": BrowserEnvironment.TEST,
    "ci": BrowserEnvironment.TEST,
    "staging": BrowserEnvironment.STAGING,
    "stage": BrowserEnvironment.STAGING,
    "prod": BrowserEnvironment.PRODUCTION,
    "production": BrowserEnvironment.PRODUCTION,
    "live": BrowserEnvironment.PRODUCTION,
}

ALLOWED_SCHEMES_DEFAULT = frozenset({"http", "https"})
PROHIBITED_SCHEMES = frozenset({
    "file", "javascript", "data", "vbscript", "blob", "about",
    "chrome", "chrome-extension", "view-source", "ws", "wss",
})

_METADATA_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
})

# Default per-environment allow hosts (exact or explicit subdomain roots)
_DEFAULT_ALLOW: dict[BrowserEnvironment, tuple[str, ...]] = {
    BrowserEnvironment.DEVELOPMENT: (
        "localhost", "127.0.0.1", "::1",
        "example.com", "example.org", "example.net",
        "httpbin.org", "saathi.local", "staging.saathi.local",
    ),
    BrowserEnvironment.TEST: (
        "localhost", "127.0.0.1", "::1",
        "example.com", "example.org", "example.net",
        "httpbin.org", "saathi.local",
    ),
    BrowserEnvironment.STAGING: (
        "example.com", "example.org", "example.net",
        "staging.saathi.local", "saathi.local",
    ),
    BrowserEnvironment.PRODUCTION: (
        # Deny-by-default: empty production allowlist until explicitly configured.
        # Operators must set SAATHI_BROWSER_ALLOWED_DOMAINS or pass allowed_hosts.
    ),
}

# Explicit denylist always applied
#
# Two kinds of host live here. The metadata endpoints are the classic SSRF
# targets. The rest are the NO_PROTECTED_SCRAPING invariant expressed as code:
# NEPSE's own portal, the depository, and broker trading-management systems are
# authenticated or bot-protected surfaces belonging to the exchange and to
# individual investors. They are denied at the policy layer rather than merely
# left out of an allowlist, so that widening the allowlist — which is a routine,
# low-ceremony act — can never quietly reach them.
PROTECTED_MARKET_HOSTS = frozenset({
    "nepalstock.com.np",          # NEPSE's own portal (token/WAF protected)
    "www.nepalstock.com.np",
    "newweb.nepalstock.com.np",
    "meroshare.cdsc.com.np",      # CDSC depository — investor credentials
    "cdsc.com.np",
    "tms.nepsetms.com.np",        # broker trading-management systems
    "nepsetms.com.np",
})

DEFAULT_DENY_HOSTS = frozenset({
    "metadata.google.internal",
    "metadata",
}) | PROTECTED_MARKET_HOSTS


@dataclass(frozen=True)
class NormalizedUrl:
    original: str
    scheme: str
    host: str  # lowercased, no trailing dot, punycode where possible
    port: int | None
    path: str
    origin: str
    is_ip: bool
    ip_kind: str = ""  # loopback | private | link_local | multicast | public | reserved | ""
    is_localhost: bool = False
    idn_flagged: bool = False
    mixed_script: bool = False
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainPolicyDecision:
    allowed: bool
    reason: str
    environment: str = ""
    origin: str = ""
    host: str = ""
    scheme: str = ""
    normalized: Optional[NormalizedUrl] = None
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "environment": self.environment,
            "origin": self.origin,
            "host": self.host,
            "scheme": self.scheme,
            "details": dict(self.details),
        }


def resolve_environment(name: str | None = None) -> BrowserEnvironment:
    raw = (
        name
        or os.environ.get("SAATHI_BROWSER_ENV")
        or os.environ.get("SAATHI_ENV")
        or os.environ.get("SAATHI_ENVIRONMENT")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("ENV")
        or "development"
    )
    key = str(raw).strip().lower()
    return _ENV_ALIASES.get(key, BrowserEnvironment.DEVELOPMENT)


def _has_mixed_scripts(label: str) -> bool:
    """Detect mixed-script host labels (basic deceptive Unicode protection)."""
    scripts = set()
    for ch in label:
        if ch in ".-_" or ch.isdigit():
            continue
        try:
            name = unicodedata.name(ch, "")
        except ValueError:
            continue
        if "LATIN" in name:
            scripts.add("LATIN")
        elif "CYRILLIC" in name:
            scripts.add("CYRILLIC")
        elif "GREEK" in name:
            scripts.add("GREEK")
        elif "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name:
            scripts.add("CJK")
        elif "ARABIC" in name:
            scripts.add("ARABIC")
    return len(scripts) > 1


def _to_ascii_host(host: str) -> tuple[str, bool, bool]:
    """Return (ascii_host, idn_flagged, mixed_script)."""
    if not host:
        return "", False, False
    mixed = any(_has_mixed_scripts(part) for part in host.split("."))
    idn = False
    try:
        # idna encodes Unicode → punycode
        ascii_host = host.encode("idna").decode("ascii")
        if ascii_host != host.lower() or host.lower().startswith("xn--") or ".xn--" in host.lower():
            idn = True
        return ascii_host.lower(), idn, mixed
    except Exception:
        return host.lower(), True, mixed


def _classify_ip(host: str) -> tuple[bool, str]:
    h = host.strip("[]")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False, ""
    if ip.is_loopback:
        return True, "loopback"
    if ip.is_link_local:
        return True, "link_local"
    if ip.is_private:
        return True, "private"
    if ip.is_multicast:
        return True, "multicast"
    if ip.is_reserved or ip.is_unspecified:
        return True, "reserved"
    if str(ip) == "169.254.169.254":
        return True, "link_local"
    return True, "public"


_DECIMAL_IP_RE = re.compile(r"^\d{8,10}$")
_OCTAL_IP_RE = re.compile(r"^0[0-7]+(\.0[0-7]+){3}$")
_HEX_IP_RE = re.compile(r"^0x[0-9a-fA-F]+$")


def _decode_alt_ip(host: str) -> str | None:
    """Detect alternative IP representations (decimal/hex/octal)."""
    h = host.strip().lower()
    if _HEX_IP_RE.match(h):
        try:
            n = int(h, 16)
            return str(ipaddress.IPv4Address(n))
        except Exception:
            return None
    if _DECIMAL_IP_RE.match(h):
        try:
            n = int(h, 10)
            if 0 <= n <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(n))
        except Exception:
            return None
    if _OCTAL_IP_RE.match(h):
        try:
            parts = [str(int(p, 8)) for p in h.split(".")]
            return ".".join(parts)
        except Exception:
            return None
    return None


def normalize_url(url: str) -> NormalizedUrl:
    """Deterministic URL/host normalization for policy evaluation."""
    issues: list[str] = []
    if not url or not isinstance(url, str):
        return NormalizedUrl(
            original=url or "", scheme="", host="", port=None, path="",
            origin="", is_ip=False, issues=("empty_url",),
        )
    raw = url.strip()
    # Reject whitespace / control characters in host path early
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    host_raw = (p.hostname or "")
    if host_raw.endswith("."):
        host_raw = host_raw[:-1]
        issues.append("trailing_dot_normalized")
    host_raw = host_raw.lower()
    # Alternative IP forms
    alt = _decode_alt_ip(host_raw)
    if alt:
        host_raw = alt
        issues.append("alt_ip_decoded")

    ascii_host, idn_flagged, mixed = _to_ascii_host(host_raw)
    if mixed:
        issues.append("mixed_script_host")
    if idn_flagged:
        issues.append("idn_or_punycode")

    is_ip, ip_kind = _classify_ip(ascii_host)
    is_localhost = ascii_host in ("localhost", "127.0.0.1", "::1") or ip_kind == "loopback"

    port = p.port
    # Normalize default ports out of origin
    origin_host = ascii_host
    if ":" in origin_host and not origin_host.startswith("["):
        # IPv6 without brackets already handled by urlparse
        pass
    if is_ip and ":" in ascii_host and not ascii_host.startswith("["):
        origin_netloc = f"[{ascii_host}]"
    else:
        origin_netloc = ascii_host
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        origin_netloc = f"{origin_netloc}:{port}"
    origin = f"{scheme}://{origin_netloc}" if scheme and origin_netloc else ""

    path = p.path or "/"
    if not ascii_host and scheme not in PROHIBITED_SCHEMES and scheme:
        issues.append("missing_host")

    return NormalizedUrl(
        original=raw,
        scheme=scheme,
        host=ascii_host,
        port=port,
        path=path,
        origin=origin,
        is_ip=is_ip,
        ip_kind=ip_kind,
        is_localhost=is_localhost,
        idn_flagged=idn_flagged,
        mixed_script=mixed,
        issues=tuple(issues),
    )


def _host_matches_allow(host: str, allowed: Iterable[str], *, allow_subdomains: bool) -> bool:
    """Exact host match or explicit subdomain-of allowed root (not suffix substring)."""
    host = host.lower().rstrip(".")
    for entry in allowed:
        a = str(entry).lower().strip().lstrip(".").rstrip(".")
        if not a:
            continue
        if a.startswith("*."):
            # Explicit single-level or multi-level subdomain wildcard only when
            # configured; production rejects unrestricted wildcards elsewhere.
            root = a[2:]
            if host != root and host.endswith("." + root) and host != root:
                return True
            continue
        if host == a:
            return True
        if allow_subdomains and host.endswith("." + a):
            # Prevent example.com.attacker.test matching example.com via wrong suffix
            # (endswith ".example.com" would not match attacker.test case correctly —
            # host.endswith("." + a) for a=example.com on example.com.attacker.test
            # is False because host ends with .attacker.test)
            return True
    return False


@dataclass
class DomainPolicyConfig:
    environment: BrowserEnvironment = BrowserEnvironment.DEVELOPMENT
    allowed_hosts: tuple[str, ...] = ()
    denied_hosts: tuple[str, ...] = ()
    allowed_schemes: frozenset[str] = ALLOWED_SCHEMES_DEFAULT
    allow_subdomains: bool = False
    allow_localhost: bool = False
    allow_private_networks: bool = False
    allow_ip_literals: bool = False
    allow_file: bool = False
    allow_custom_protocols: bool = False
    allow_http: bool = True  # production forces https unless exception
    require_https: bool = False
    allow_idn: bool = True  # still flagged; production may deny mixed-script
    deny_mixed_script: bool = True
    allow_wildcards: bool = False
    # Temporary governed exceptions (narrow); empty by default
    temporary_exceptions: tuple[dict, ...] = ()

    @classmethod
    def for_environment(
        cls,
        environment: str | BrowserEnvironment | None = None,
        *,
        allowed_hosts: Iterable[str] | None = None,
    ) -> "DomainPolicyConfig":
        env = (
            environment if isinstance(environment, BrowserEnvironment)
            else resolve_environment(
                environment.value if isinstance(environment, BrowserEnvironment) else environment
            )
        )
        defaults = list(_DEFAULT_ALLOW.get(env, ()))
        # Optional env-configured allowlist (comma-separated exact hosts)
        env_hosts = os.environ.get("SAATHI_BROWSER_ALLOWED_DOMAINS", "").strip()
        if env_hosts:
            defaults.extend(h.strip().lower() for h in env_hosts.split(",") if h.strip())
        if allowed_hosts is not None:
            hosts = tuple(str(h).lower().strip().lstrip(".") for h in allowed_hosts if h)
        else:
            hosts = tuple(defaults)

        if env == BrowserEnvironment.PRODUCTION:
            return cls(
                environment=env,
                allowed_hosts=hosts,
                denied_hosts=tuple(DEFAULT_DENY_HOSTS),
                allowed_schemes=frozenset({"https"}),
                allow_subdomains=False,
                allow_localhost=False,
                allow_private_networks=False,
                allow_ip_literals=False,
                allow_file=False,
                allow_custom_protocols=False,
                allow_http=False,
                require_https=True,
                allow_idn=True,
                deny_mixed_script=True,
                allow_wildcards=False,
            )
        if env == BrowserEnvironment.STAGING:
            return cls(
                environment=env,
                allowed_hosts=hosts,
                denied_hosts=tuple(DEFAULT_DENY_HOSTS),
                allowed_schemes=frozenset({"http", "https"}),
                allow_subdomains=False,
                allow_localhost=False,
                allow_private_networks=False,
                allow_ip_literals=False,
                allow_file=False,
                allow_custom_protocols=False,
                allow_http=True,
                require_https=False,
                deny_mixed_script=True,
                allow_wildcards=False,
            )
        # development / test
        return cls(
            environment=env,
            allowed_hosts=hosts,
            denied_hosts=tuple(DEFAULT_DENY_HOSTS),
            allowed_schemes=frozenset({"http", "https"}),
            allow_subdomains=True,  # only for listed roots, not arbitrary suffix
            allow_localhost=True,
            allow_private_networks=False,
            allow_ip_literals=True,  # loopback only still enforced below
            allow_file=False,
            allow_custom_protocols=False,
            allow_http=True,
            require_https=False,
            deny_mixed_script=True,
            allow_wildcards=False,
        )


class DomainPolicyService:
    """Canonical environment-aware domain policy evaluator."""

    def __init__(self, config: DomainPolicyConfig | None = None):
        self.config = config or DomainPolicyConfig.for_environment()

    @classmethod
    def for_environment(
        cls,
        environment: str | BrowserEnvironment | None = None,
        *,
        allowed_hosts: Iterable[str] | None = None,
    ) -> "DomainPolicyService":
        return cls(DomainPolicyConfig.for_environment(
            environment, allowed_hosts=allowed_hosts,
        ))

    def check(self, url: str, *, allowed_hosts: Iterable[str] | None = None) -> DomainPolicyDecision:
        cfg = self.config
        env_name = cfg.environment.value
        norm = normalize_url(url)
        if "empty_url" in norm.issues:
            return DomainPolicyDecision(False, "empty_url", environment=env_name)

        scheme = norm.scheme
        if not scheme:
            return DomainPolicyDecision(
                False, "missing_scheme", environment=env_name, normalized=norm,
            )
        if scheme in PROHIBITED_SCHEMES:
            if scheme == "file" and not cfg.allow_file:
                return DomainPolicyDecision(
                    False, "file_scheme_denied", environment=env_name,
                    scheme=scheme, normalized=norm,
                )
            if scheme == "javascript":
                return DomainPolicyDecision(
                    False, "javascript_scheme_denied", environment=env_name,
                    scheme=scheme, normalized=norm,
                )
            if scheme == "data":
                return DomainPolicyDecision(
                    False, "data_scheme_denied", environment=env_name,
                    scheme=scheme, normalized=norm,
                )
            return DomainPolicyDecision(
                False, f"dangerous_or_unsupported_scheme:{scheme}",
                environment=env_name, scheme=scheme, normalized=norm,
            )
        if scheme not in cfg.allowed_schemes:
            if not cfg.allow_custom_protocols:
                return DomainPolicyDecision(
                    False, f"custom_or_disallowed_scheme:{scheme}",
                    environment=env_name, scheme=scheme, normalized=norm,
                )
            return DomainPolicyDecision(
                False, f"scheme_not_allowed:{scheme}",
                environment=env_name, scheme=scheme, normalized=norm,
            )
        if cfg.require_https and scheme != "https":
            return DomainPolicyDecision(
                False, "https_required", environment=env_name,
                scheme=scheme, host=norm.host, origin=norm.origin, normalized=norm,
            )

        host = norm.host
        if not host:
            return DomainPolicyDecision(
                False, "missing_host", environment=env_name, scheme=scheme, normalized=norm,
            )

        if host in _METADATA_HOSTS or host.endswith(".metadata.google.internal"):
            return DomainPolicyDecision(
                False, "cloud_metadata", environment=env_name,
                host=host, scheme=scheme, origin=norm.origin, normalized=norm,
            )

        # Deny list
        deny = set(cfg.denied_hosts) | set(DEFAULT_DENY_HOSTS)
        if host in deny or any(host.endswith("." + d) for d in deny if d):
            return DomainPolicyDecision(
                False, "domain_denylisted", environment=env_name,
                host=host, scheme=scheme, origin=norm.origin, normalized=norm,
            )

        if norm.mixed_script and cfg.deny_mixed_script:
            return DomainPolicyDecision(
                False, "mixed_script_host_denied", environment=env_name,
                host=host, scheme=scheme, origin=norm.origin, normalized=norm,
                details={"idn": norm.idn_flagged},
            )

        # Localhost / loopback
        if norm.is_localhost or norm.ip_kind == "loopback":
            if not cfg.allow_localhost:
                return DomainPolicyDecision(
                    False, "localhost_denied", environment=env_name,
                    host=host, scheme=scheme, origin=norm.origin, normalized=norm,
                )

        # Private / reserved IPs
        if norm.is_ip:
            if not cfg.allow_ip_literals and not (
                cfg.allow_localhost and norm.ip_kind == "loopback"
            ):
                return DomainPolicyDecision(
                    False, "ip_literal_denied", environment=env_name,
                    host=host, scheme=scheme, origin=norm.origin, normalized=norm,
                    details={"ip_kind": norm.ip_kind},
                )
            if norm.ip_kind in ("private", "link_local", "multicast", "reserved"):
                if not cfg.allow_private_networks:
                    return DomainPolicyDecision(
                        False, f"private_or_link_local_ip",
                        environment=env_name, host=host, scheme=scheme,
                        origin=norm.origin, normalized=norm,
                        details={"ip_kind": norm.ip_kind},
                    )

        # Wildcard policy
        allow = tuple(allowed_hosts) if allowed_hosts is not None else cfg.allowed_hosts
        if any(str(a).startswith("*.") or str(a) == "*" for a in allow):
            if not cfg.allow_wildcards or cfg.environment == BrowserEnvironment.PRODUCTION:
                # Reject unrestricted wildcards in production always
                if cfg.environment == BrowserEnvironment.PRODUCTION:
                    return DomainPolicyDecision(
                        False, "wildcard_denied_in_production",
                        environment=env_name, host=host, scheme=scheme,
                        origin=norm.origin, normalized=norm,
                    )

        # Empty production allowlist → deny
        if not allow:
            return DomainPolicyDecision(
                False, "domain_not_allowlisted",
                environment=env_name, host=host, scheme=scheme,
                origin=norm.origin, normalized=norm,
                details={"empty_allowlist": True},
            )

        # Temporary exceptions (narrow, expiry-checked)
        for exc in cfg.temporary_exceptions:
            if self._exception_matches(exc, host, scheme, norm.port):
                return DomainPolicyDecision(
                    True, "temporary_exception",
                    environment=env_name, host=host, scheme=scheme,
                    origin=norm.origin, normalized=norm,
                    details={"exception_id": exc.get("exception_id", "")},
                )

        if not _host_matches_allow(host, allow, allow_subdomains=cfg.allow_subdomains):
            return DomainPolicyDecision(
                False, "domain_not_allowlisted",
                environment=env_name, host=host, scheme=scheme,
                origin=norm.origin, normalized=norm,
            )

        return DomainPolicyDecision(
            True, "ok",
            environment=env_name, host=host, scheme=scheme,
            origin=norm.origin, normalized=norm,
        )

    def _exception_matches(self, exc: dict, host: str, scheme: str, port: int | None) -> bool:
        import time
        if not exc or exc.get("status", "active") != "active":
            return False
        expiry = float(exc.get("expiry_time") or 0)
        if expiry and time.time() > expiry:
            return False
        # Prohibited schemes never via exception
        if scheme in PROHIBITED_SCHEMES:
            return False
        if scheme in ("file", "javascript", "data"):
            return False
        max_uses = exc.get("maximum_uses")
        current = int(exc.get("uses") or 0)
        if max_uses is not None and current >= int(max_uses):
            return False
        exc_domain = str(exc.get("domain") or "").lower().rstrip(".")
        if not exc_domain or host != exc_domain:
            return False
        if exc.get("scheme") and scheme != str(exc["scheme"]).lower():
            return False
        if exc.get("port") is not None and port != int(exc["port"]):
            return False
        # Never allow financial/withdrawal via exception alone
        classes = set(exc.get("allowed_action_classes") or [])
        if "financial" in classes or "withdrawal" in classes:
            return False
        return True

    def check_redirect(
        self, original_url: str, final_url: str, **kwargs,
    ) -> DomainPolicyDecision:
        d = self.check(final_url, **kwargs)
        if not d.allowed:
            return DomainPolicyDecision(
                False, f"redirect_denied:{d.reason}",
                environment=d.environment, origin=d.origin,
                host=d.host, scheme=d.scheme, normalized=d.normalized,
                details={"original": original_url, **d.details},
            )
        return d

    def check_popup(self, popup_url: str, **kwargs) -> DomainPolicyDecision:
        d = self.check(popup_url, **kwargs)
        if not d.allowed:
            return DomainPolicyDecision(
                False, f"popup_denied:{d.reason}",
                environment=d.environment, origin=d.origin,
                host=d.host, scheme=d.scheme, normalized=d.normalized,
                details=d.details,
            )
        return d


# ── Back-compat helpers used by existing policy.py / callers ─────────────────


def check_domain_env(
    url: str,
    *,
    environment: str = "development",
    allowed_hosts: Iterable[str] | None = None,
    allow_private: bool = False,
) -> DomainPolicyDecision:
    cfg = DomainPolicyConfig.for_environment(environment, allowed_hosts=allowed_hosts)
    if allow_private:
        cfg.allow_private_networks = True
        cfg.allow_ip_literals = True
    return DomainPolicyService(cfg).check(url)


def production_config_violations(
    *,
    environment: str | None = None,
    allowed_hosts: Iterable[str] | None = None,
    raw_browser_enabled: bool = False,
    allow_file: bool = False,
    allow_private: bool = False,
    allow_custom_protocols: bool = False,
    allow_wildcards: bool = False,
    screenshot_without_redaction: bool = False,
    traces_without_policy: bool = False,
    unrestricted_desktop: bool = False,
    browser_enabled: bool = True,
) -> list[dict]:
    """Blocking production configuration violations (privacy-safe)."""
    env = resolve_environment(environment)
    if env != BrowserEnvironment.PRODUCTION:
        return []
    issues: list[dict] = []
    if raw_browser_enabled:
        issues.append({
            "code": "RAW_BROWSER_IN_PRODUCTION",
            "message": "SAATHI_ALLOW_RAW_BROWSER must not be enabled in production",
        })
    hosts = list(allowed_hosts) if allowed_hosts is not None else list(
        DomainPolicyConfig.for_environment(env).allowed_hosts
    )
    if browser_enabled and not hosts:
        issues.append({
            "code": "EMPTY_PRODUCTION_DOMAIN_ALLOWLIST",
            "message": "production browser execution requires a non-empty domain allowlist",
        })
    if allow_wildcards or any(h.strip() in ("*", "*.*") or h.strip() == "*" for h in hosts):
        issues.append({
            "code": "WILDCARD_DOMAIN_IN_PRODUCTION",
            "message": "unrestricted wildcard domains are prohibited in production",
        })
    if allow_file:
        issues.append({
            "code": "FILE_SCHEME_IN_PRODUCTION",
            "message": "file:// must not be allowed in production",
        })
    if allow_private:
        issues.append({
            "code": "PRIVATE_NETWORK_IN_PRODUCTION",
            "message": "broad private-network browser access is prohibited in production",
        })
    if allow_custom_protocols:
        issues.append({
            "code": "CUSTOM_PROTOCOLS_IN_PRODUCTION",
            "message": "unrestricted custom protocols are prohibited in production",
        })
    if screenshot_without_redaction:
        issues.append({
            "code": "SCREENSHOT_WITHOUT_REDACTION",
            "message": "screenshot capture requires a redaction or suppression policy",
        })
    if traces_without_policy:
        issues.append({
            "code": "TRACES_WITHOUT_POLICY",
            "message": "browser traces require explicit retention and redaction policy",
        })
    if unrestricted_desktop:
        issues.append({
            "code": "UNRESTRICTED_DESKTOP_CONTROL",
            "message": "Human Mac unrestricted desktop control is prohibited",
        })
    return issues
