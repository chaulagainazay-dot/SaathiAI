"""Resource bounds for single-host multi-worker fleet (M2 / 8 GB class).

Pressure reduces concurrency or pauses scheduling; never crashes the platform.
"""
from __future__ import annotations

# Process / worker bounds
MAX_WORKER_PROCESSES = 4
MAX_ACTIVE_WORKERS = 4
MAX_ACTIVE_LEASES = 8
MAX_CONCURRENT_MODEL_JOBS = 1
MAX_CONCURRENT_BROWSER_JOBS = 1
MAX_CONCURRENT_TOOL_EXECUTIONS = 2
MAX_WORKER_QUEUE_DEPTH = 16

# Per-task budgets
PER_TASK_MEMORY_MB = 512
PER_TASK_TIMEOUT_SEC = 120.0
DEFAULT_LEASE_TTL_SEC = 60.0
MAX_LEASE_TTL_SEC = 300.0
MAX_LEASE_RENEWALS = 20
MAX_RETRY_COUNT = 3
MAX_RECOVERY_ATTEMPTS = 5

# Heartbeat / events
HEARTBEAT_INTERVAL_SEC = 5.0
HEARTBEAT_TIMEOUT_SEC = 20.0
MAX_HEARTBEAT_PAYLOAD_BYTES = 4096
MAX_EVENT_PAYLOAD_BYTES = 16384
MAX_ARTIFACT_BYTES = 256 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_RETAINED_EVENTS = 200

# Transport
PROTOCOL_VERSION = "fleet.v1"
RUNTIME_VERSION = "m103.fleet.v1"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
ALLOWED_BIND_HOST = "127.0.0.1"

# Phase authorization (Phase A only certified)
PHASE_A_SINGLE_HOST = "PHASE_A_SINGLE_HOST"
PHASE_B_TRUSTED_LAN = "PHASE_B_TRUSTED_LAN"  # defined, not authorized
PHASE_C_SECURE_REMOTE = "PHASE_C_SECURE_REMOTE"  # defined, not authorized
PHASE_D_CLOUD = "PHASE_D_CLOUD"  # defined, not authorized
AUTHORIZED_PHASES = frozenset({PHASE_A_SINGLE_HOST})

# Scheduling pressure thresholds (0–100)
CPU_PRESSURE_PAUSE = 90
MEMORY_PRESSURE_PAUSE = 85
DISK_PRESSURE_PAUSE = 90

KNOWN_CAPABILITIES = frozenset(
    {
        "planning",
        "analysis",
        "coding",
        "testing",
        "browser",
        "documentation",
        "security_review",
        "certification",
        "local_model_inference",
        "speech",
        "knowledge_indexing",
        "read_only_repository_access",
        "approved_mutation",
        "platform-agent-runtime",  # M56 compatibility
    }
)

FORBIDDEN_CAPABILITIES = frozenset(
    {
        "direct_tool_execution",
        "forge_approval",
        "mint_capability",
        "public_listener",
        "production_mutation",
        "trading_live",
        "credential_access",
        "shell_transport",
    }
)
