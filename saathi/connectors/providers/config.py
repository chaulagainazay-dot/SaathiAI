"""M32 — Provider configuration (no secrets; endpoint allowlisting; fail closed).

Configuration is declarative and secret-free. Callers can never supply an
endpoint, auth mechanism, timeout escalation, or retry escalation. Production
environment is disabled. External endpoints require HTTPS; loopback is allowed
only for deterministic local/simulation transports.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from saathi.connectors.providers.models import (
    DataClassification,
    M32_PERMITTED_DATA_CLASSES,
    M32_PERMITTED_SIDE_EFFECTS,
    ProviderSideEffectClass,
)

# Environments that are permitted to be enabled in M32
PERMITTED_ENVIRONMENTS = frozenset({"local", "test", "sandbox", "dev"})
# Production stays disabled in M32 regardless of any other field
DISABLED_ENVIRONMENTS = frozenset({"production", "prod", "live"})

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "loopback", "inprocess"})

# Hard ceilings — caller cannot escalate beyond these
MAX_TIMEOUT_SECONDS = 30.0
MAX_TOTAL_DEADLINE = 30.0
MAX_RETRIES = 3
MAX_RESPONSE_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 64 * 1024
MAX_CONCURRENCY = 4


@dataclass
class TimeoutPolicy:
    connect_seconds: float = 2.0
    read_seconds: float = 3.0
    total_deadline: float = 5.0

    def clamp(self) -> "TimeoutPolicy":
        self.connect_seconds = max(0.05, min(float(self.connect_seconds), MAX_TIMEOUT_SECONDS))
        self.read_seconds = max(0.05, min(float(self.read_seconds), MAX_TIMEOUT_SECONDS))
        self.total_deadline = max(0.1, min(float(self.total_deadline), MAX_TOTAL_DEADLINE))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetryPolicy:
    max_retries: int = 1
    backoff_base_seconds: float = 0.01   # deterministic, tiny for tests
    backoff_factor: float = 2.0
    respect_retry_after: bool = True

    def clamp(self) -> "RetryPolicy":
        self.max_retries = max(0, min(int(self.max_retries), MAX_RETRIES))
        self.backoff_base_seconds = max(0.0, min(float(self.backoff_base_seconds), 1.0))
        self.backoff_factor = max(1.0, min(float(self.backoff_factor), 4.0))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RateLimitPolicy:
    requests_per_minute: int = 60
    max_retry_after_seconds: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderConfig:
    provider_id: str
    environment: str = "test"
    endpoint_reference: str = "inprocess://saathi.echo"  # symbolic; never caller-supplied
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    rate_limit_policy: RateLimitPolicy = field(default_factory=RateLimitPolicy)
    auth_profile: str = "none"
    request_size_limit: int = MAX_REQUEST_BYTES
    response_size_limit: int = MAX_RESPONSE_BYTES
    allowed_operations: tuple[str, ...] = ()
    data_classification: str = DataClassification.PUBLIC.value
    side_effect_class: str = ProviderSideEffectClass.READ_ONLY.value
    enabled: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.allowed_operations, list):
            self.allowed_operations = tuple(self.allowed_operations)
        self.timeout_policy.clamp()
        self.retry_policy.clamp()
        self.request_size_limit = max(1, min(int(self.request_size_limit), MAX_REQUEST_BYTES))
        self.response_size_limit = max(1, min(int(self.response_size_limit), MAX_RESPONSE_BYTES))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class ConfigError(ValueError):
    """Raised when a provider configuration fails closed."""


def validate_config(config: ProviderConfig) -> None:
    """Fail closed on any unsafe or unknown configuration. Raises ConfigError."""
    env = (config.environment or "").strip().lower()
    if env in DISABLED_ENVIRONMENTS:
        raise ConfigError(f"environment_disabled:{env}")
    if env not in PERMITTED_ENVIRONMENTS:
        raise ConfigError(f"unknown_environment:{env}")

    # side-effect ceiling
    try:
        sec = ProviderSideEffectClass(config.side_effect_class)
    except ValueError:
        raise ConfigError(f"unknown_side_effect_class:{config.side_effect_class}")
    if sec not in M32_PERMITTED_SIDE_EFFECTS:
        raise ConfigError(f"side_effect_not_permitted:{sec.value}")

    # data classification ceiling
    try:
        dc = DataClassification(config.data_classification)
    except ValueError:
        raise ConfigError(f"unknown_data_classification:{config.data_classification}")
    if dc not in M32_PERMITTED_DATA_CLASSES:
        raise ConfigError(f"data_classification_not_permitted:{dc.value}")

    # auth profile must be secret-free for the pilot
    if (config.auth_profile or "none").lower() not in ("none", "public", "sandbox_none"):
        raise ConfigError(f"auth_profile_requires_secret:{config.auth_profile}")

    _validate_endpoint(config.endpoint_reference)


def _validate_endpoint(endpoint: str) -> None:
    ep = (endpoint or "").strip()
    if not ep:
        raise ConfigError("endpoint_required")
    parsed = urlparse(ep)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme in ("inprocess", "loopback"):
        return  # deterministic local transport
    if scheme == "http":
        if host in LOOPBACK_HOSTS:
            return  # loopback allowed for deterministic tests
        raise ConfigError("external_http_requires_tls")
    if scheme == "https":
        if not host:
            raise ConfigError("https_host_required")
        return
    raise ConfigError(f"endpoint_scheme_not_allowed:{scheme or 'none'}")


# Caller-supplied fields that must never override configuration
CALLER_FORBIDDEN_CONFIG_KEYS = frozenset({
    "endpoint", "endpoint_reference", "url", "base_url", "auth", "auth_profile",
    "authorization", "timeout", "timeout_policy", "retry", "retry_policy",
    "max_retries", "headers", "connect_timeout", "read_timeout", "deadline_override",
})


def caller_attempts_config_override(metadata: Optional[dict[str, Any]]) -> Optional[str]:
    """Return the offending key if caller metadata tries to override config, else None."""
    if not metadata:
        return None
    for k in metadata:
        if str(k).lower() in CALLER_FORBIDDEN_CONFIG_KEYS:
            return str(k).lower()
    return None
