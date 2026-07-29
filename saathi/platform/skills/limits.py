"""Resource bounds for Skill Ecosystem Runtime (M112–M120). Local-only."""
from __future__ import annotations

MANIFEST_SCHEMA_VERSION = "skill.manifest.v1"
RUNTIME_VERSION = "m112.skill.v1"
SAATHIOS_VERSION = "1.0.0-local"

MAX_DISCOVERED_PACKAGES = 64
MAX_INSTALLED_VERSIONS_PER_SKILL = 8
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 512 * 1024
MAX_PACKAGE_FILES = 32
MAX_DEPENDENCY_COUNT = 8
MAX_DEPENDENCY_DEPTH = 4
MAX_CAPABILITY_COUNT = 24
MAX_TOOL_BINDINGS = 16
MAX_PERMISSION_COUNT = 24
MAX_CONCURRENT_SKILL_EXECUTIONS = 2
MAX_CONCURRENT_VALIDATIONS = 4
MAX_CONCURRENT_HEALTH_CHECKS = 4
EXECUTION_TIMEOUT_SEC = 120.0
HEALTH_TIMEOUT_SEC = 10.0
MAX_EVENT_BYTES = 16 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = 128 * 1024
MAX_RETAINED_EXECUTIONS = 200
MAX_UPGRADE_ATTEMPTS = 5
MAX_ROLLBACK_ATTEMPTS = 5
MAX_KNOWLEDGE_INGEST_BYTES = 256 * 1024

# Repository-controlled discovery roots (relative to repo root or package dir)
BUILTIN_PACKAGES_SUBDIR = "packages"
ALLOWED_ENTRYPOINT_TYPES = frozenset(
    {
        "declarative",
        "adapter_bound",
        "orchestration_template",
    }
)
FORBIDDEN_ENTRYPOINT_TYPES = frozenset(
    {
        "shell",
        "python_import",
        "eval",
        "remote_url",
        "subprocess",
    }
)

KNOWN_CAPABILITIES = frozenset(
    {
        "repository.read",
        "repository.analyze",
        "repository.propose_patch",
        "test.run",
        "browser.inspect",
        "browser.certify",
        "knowledge.search",
        "knowledge.ingest",
        "document.generate",
        "report.generate",
        "hcg.analyze",
        "hcg.operations.plan",
        "ielts.content.generate",
        "ielts.readiness.review",
        "travel.plan",
        "voice.speak",
        "model.local.generate",
        "portfolio.analyze_readonly",
        "mutation.safe_test",
    }
)

FORBIDDEN_PERMISSIONS = frozenset(
    {
        "production_credentials",
        "payment_systems",
        "live_databases",
        "trading_accounts",
        "deployment_credentials",
        "unrestricted_shell",
        "place_order",
        "withdraw",
        "disable_kill_switch",
        "direct_tool_execution",
        "forge_approval",
        "mint_capability",
    }
)

# Tools that skills may bind (must exist in ToolRegistry when available)
KNOWN_SAFE_TOOLS = frozenset(
    {
        "m49.echo_readonly",
        "m49.local_note_write",
    }
)
