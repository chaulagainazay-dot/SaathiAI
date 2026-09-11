"""FM-I6 LocalModelHarness contracts, pins, and readiness types.

Design-only decisions from FM-I5 are encoded as constants. This module never
starts, stops, or pulls Ollama and never grants tool or production authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse


# ── Pins (FM-I5) ────────────────────────────────────────────────────────────

HARNESS_ID = "local-model"
HARNESS_VERSION = "0.1.0"
PROTOCOL_VERSION = "1.0"
MILESTONE = "FM-I6"
PRODUCTION_CERTIFIED = False

PINNED_RUNTIME = "OLLAMA_SELECTED"
PINNED_RUNTIME_VERSION = "0.32.5"
PROCESS_OWNERSHIP = "USER_MANAGED_RUNTIME"

PINNED_MODEL = "qwen2.5:1.5b"
PINNED_MODEL_DIGEST = (
    "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"
)

# Only structural loopback endpoint permitted (no env override by default).
ALLOWED_ENDPOINT = "http://127.0.0.1:11434"
ALLOWED_HOST = "127.0.0.1"
ALLOWED_PORT = 11434
ALLOWED_SCHEME = "http"

# Context / output budgets (tokens approximated as chars/4).
MAX_CONTEXT_TOKENS = 2048
RESERVED_OUTPUT_TOKENS = 256
MAX_OUTPUT_TOKENS = 512
SYSTEM_POLICY_TOKEN_BUDGET = 384
HISTORY_TOKEN_BUDGET = 1024
TOOL_RESULT_TOKEN_BUDGET = 384
USER_TURN_TOKEN_BUDGET = 512

# Timeouts (seconds)
CONNECT_TIMEOUT_S = 2.0
FIRST_TOKEN_TIMEOUT_S = 30.0
INTER_TOKEN_TIMEOUT_S = 15.0
TOTAL_TURN_TIMEOUT_S = 90.0
CANCEL_GRACE_S = 10.0
MODEL_LOAD_WAIT_S = 60.0

# Stream limits
MAX_NDJSON_LINE_BYTES = 64 * 1024
MAX_STREAM_RESPONSE_BYTES = 256 * 1024
MAX_DELTA_CHARS = 4096
MAX_OUTPUT_CHARS_DEFAULT = 4096

# Resource gates — FM-I6.2-MG-FIX combined macOS gate (see local_model_memory_gate.py).
# Legacy names retained for import compatibility; values are NOT pure-free floors.
# Primary admission uses CombinedMacOSMemoryGate, not these alone.
MIN_FREE_MEMORY_PERCENT = 20  # Darwin memory_pressure free% floor (not pure free pages)
MIN_AVAILABLE_MEMORY_MIB = 2048.0  # absolute reclaimable floor (raised from 1024 by MG-FIX)
MAX_ACTIVE_LOCAL_SESSIONS = 1
MAX_TRANSIENT_CONNECT_RETRIES = 1
MEMORY_GATE_POLICY_VERSION = "fm_i6_2_mg_fix.combined_macos.v1"

DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.9

SAFE_SYSTEM_POLICY = (
    "You are an untrusted local assistant driver for SaathiOS. "
    "You do not have credentials, approval power, tool execution, filesystem, "
    "browser, network, or trading authority. Answer in plain text only. "
    "If proposing a tool, emit ONLY a single JSON object with keys "
    "proposal_id, requested_tool_name, arguments, rationale_summary, "
    "confidence, request_correlation_id inside a "
    "<tool_proposal>...</tool_proposal> block. "
    "Never claim actions already executed. Never invent approval or scope IDs. "
    "Never request or echo secrets. Never include private chain-of-thought."
)

# Fields that must never leave the model surface.
PRIVATE_COT_KEYS = frozenset({
    "chain_of_thought",
    "private_cot",
    "hidden_reasoning",
    "raw_cot",
    "thinking",
    "reasoning",
    "reasoning_content",
})

# Model-supplied fields forbidden inside tool proposals (scope forgery).
FORBIDDEN_PROPOSAL_KEYS = frozenset({
    "organization_id",
    "workspace_id",
    "mission_id",
    "run_id",
    "session_id",
    "tool_intent_id",
    "approval_id",
    "approval_ref",
    "execution_id",
    "permissions",
    "credentials",
    "credential",
    "api_key",
    "token",
    "password",
    "policy_level",
    "trading_guardian",
    "tg_decision",
    "rbac",
    "scope",
})


class LocalReadinessState(str, Enum):
    UNCONFIGURED = "UNCONFIGURED"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    RUNTIME_HEALTHY = "RUNTIME_HEALTHY"
    MODEL_NOT_INSTALLED = "MODEL_NOT_INSTALLED"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    MODEL_AVAILABLE = "MODEL_AVAILABLE"
    MODEL_LOADING = "MODEL_LOADING"
    MODEL_READY = "MODEL_READY"
    DEGRADED = "DEGRADED"
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE"
    QUARANTINED = "QUARANTINED"
    BINDING_UNSAFE = "BINDING_UNSAFE"


class LocalFailureKind(str, Enum):
    ENDPOINT_INVALID = "ENDPOINT_INVALID"
    ENDPOINT_NON_LOOPBACK = "ENDPOINT_NON_LOOPBACK"
    ENDPOINT_UNAVAILABLE = "ENDPOINT_UNAVAILABLE"
    BINDING_UNSAFE = "BINDING_UNSAFE"
    RUNTIME_VERSION_UNSUPPORTED = "RUNTIME_VERSION_UNSUPPORTED"
    MODEL_NOT_INSTALLED = "MODEL_NOT_INSTALLED"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    MODEL_LOAD_FAILURE = "MODEL_LOAD_FAILURE"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    MALFORMED_STREAM = "MALFORMED_STREAM"
    MALFORMED_JSON = "MALFORMED_JSON"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    MEMORY_PRESSURE = "RESOURCE_PRESSURE"
    OUTPUT_LIMIT = "OUTPUT_LIMIT"
    TOOL_PROPOSAL_VIOLATION = "TOOL_PROPOSAL_VIOLATION"
    SCOPE_FORGERY = "SCOPE_FORGERY"
    SECRET_SHAPED_OUTPUT = "SECRET_SHAPED_OUTPUT"
    CLASSIFICATION_REJECTED = "CLASSIFICATION_REJECTED"
    QUARANTINED = "QUARANTINED"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class LocalModelConfig:
    """Immutable harness configuration (operator-fixed; no model overrides)."""

    endpoint: str = ALLOWED_ENDPOINT
    model: str = PINNED_MODEL
    model_digest: str = PINNED_MODEL_DIGEST
    min_runtime_version: str = "0.32.0"
    max_context_tokens: int = MAX_CONTEXT_TOKENS
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    reserved_output_tokens: int = RESERVED_OUTPUT_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    synthetic_only: bool = True
    enforce_memory_gate: bool = True
    enforce_binding_gate: bool = True
    max_active_sessions: int = MAX_ACTIVE_LOCAL_SESSIONS
    max_output_chars: int = MAX_OUTPUT_CHARS_DEFAULT
    system_policy: str = SAFE_SYSTEM_POLICY

    def __post_init__(self) -> None:
        if self.max_active_sessions != 1:
            raise ValueError("FM-I6 requires max_active_sessions == 1")
        if self.max_output_tokens > MAX_OUTPUT_TOKENS:
            raise ValueError("cannot exceed absolute output ceiling")
        if self.max_context_tokens > MAX_CONTEXT_TOKENS:
            raise ValueError("cannot exceed absolute context ceiling")


@dataclass(frozen=True)
class ModelInventoryEntry:
    name: str
    digest: str
    size_bytes: int = 0


@dataclass(frozen=True)
class RuntimeInventory:
    reachable: bool
    version: str = ""
    models: Tuple[ModelInventoryEntry, ...] = ()
    loaded_models: Tuple[str, ...] = ()
    bindings: Tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class MemorySnapshot:
    """Legacy snapshot shape (transitional).

    ``free_percent`` historically mixed reclaimable-ratio semantics. Prefer
    :class:`MacOSMemorySample` / :class:`MemoryGateDecision` from
    ``local_model_memory_gate``. ``ok`` remains the admission bit for old tests.
    """

    total_bytes: int
    free_percent: float  # diagnostic; not pure free
    available_mib: float  # reclaimable MiB when produced by MG-FIX
    ok: bool
    detail: str = ""
    pure_free_percent: float = 0.0  # diagnostic only
    darwin_free_percent: float = 0.0
    policy_version: str = ""


@dataclass(frozen=True)
class StreamChunk:
    """Normalized stream unit from transport (not a HarnessEvent)."""

    text: str = ""
    done: bool = False
    error: Optional[str] = None
    raw_keys: Tuple[str, ...] = ()
    thinking_stripped: bool = False


@dataclass
class LocalMetrics:
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    cancel_count: int = 0
    timeout_count: int = 0
    malformed_stream_count: int = 0
    tool_proposal_count: int = 0
    resource_pressure_count: int = 0
    quarantine_count: int = 0
    first_token_latency_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    response_bytes: int = 0


def estimate_tokens(text: str) -> int:
    """Conservative estimator: ceil(chars/4), minimum 1 for non-empty."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def validate_loopback_endpoint(endpoint: str) -> str:
    """Structurally validate and normalize to ALLOWED_ENDPOINT or raise ValueError."""
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("endpoint required")
    raw = endpoint.strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != ALLOWED_SCHEME:
        raise ValueError(f"scheme not allowed: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise ValueError("userinfo not allowed in endpoint")
    if parsed.query or parsed.fragment:
        raise ValueError("query/fragment not allowed in endpoint")
    if parsed.path not in ("", "/"):
        raise ValueError("path not allowed on endpoint base")
    host = (parsed.hostname or "").lower()
    if host != ALLOWED_HOST:
        # Explicitly reject localhost and all non-loopback forms.
        raise ValueError(f"host not allowed: {host!r} (require {ALLOWED_HOST})")
    port = parsed.port if parsed.port is not None else (80 if parsed.scheme == "http" else 443)
    if port != ALLOWED_PORT:
        raise ValueError(f"port not allowed: {port}")
    # Rebuild canonical form (no trailing slash).
    return f"{ALLOWED_SCHEME}://{ALLOWED_HOST}:{ALLOWED_PORT}"


def version_tuple(version: str) -> Tuple[int, ...]:
    parts: list[int] = []
    for p in (version or "").split("."):
        digits = "".join(c for c in p if c.isdigit())
        if digits:
            parts.append(int(digits))
        else:
            break
    return tuple(parts) if parts else (0,)


def version_compatible(actual: str, minimum: str) -> bool:
    return version_tuple(actual) >= version_tuple(minimum)
