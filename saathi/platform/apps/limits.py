"""Resource bounds for Universal Application Runtime (M121–M129). Local only."""
from __future__ import annotations

MANIFEST_SCHEMA_VERSION = "app.manifest.v1"
RUNTIME_VERSION = "m121.app.v1"
SAATHIOS_VERSION = "1.0.0-local"

MAX_DISCOVERED_APPS = 64
MAX_INSTALLED_VERSIONS = 8
MAX_MANIFEST_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 512 * 1024
MAX_PACKAGE_FILES = 32
MAX_NAV_ITEMS = 24
MAX_PAGES = 48
MAX_DEPENDENCIES = 16
MAX_SKILLS = 16
MAX_KNOWLEDGE_SOURCES = 16
MAX_CONCURRENT_APP_OPS = 4
MAX_BACKUP_SNAPSHOTS_PER_APP = 5
MAX_WORKSPACE_CONFIG_BYTES = 64 * 1024
MAX_RETAINED_EVENTS = 200

ALLOWED_ENTRYPOINT_TYPES = frozenset({"declarative", "module_adapter", "workspace_bundle"})
FORBIDDEN_ENTRYPOINT_TYPES = frozenset({"shell", "remote_url", "python_import", "eval"})

APP_TYPES = frozenset(
    {
        "business",
        "ai",
        "dashboard",
        "operations",
        "reporting",
        "analytics",
        "education",
        "healthcare",
        "finance",
        "internal_platform",
    }
)

KNOWN_CAPABILITIES = frozenset(
    {
        "forms",
        "tables",
        "dashboards",
        "charts",
        "reports",
        "search",
        "notifications",
        "attachments",
        "workflows",
        "approvals",
        "comments",
        "activity_history",
        "tasks",
        "calendar",
        "offline_cache",
        "sync",
        "conversation",
        "knowledge",
        "skills",
        "workers",
        "missions",
    }
)
