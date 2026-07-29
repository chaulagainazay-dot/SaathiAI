"""M157 — Private-alpha release baseline and support matrix."""
from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RELEASE_VERSION = "0.1.0-private-alpha.1"
SCHEMA_VERSION = "m157.private_alpha.v1"
PLATFORM_VERSION = "m50-m156.core"
BACKUP_FORMAT_VERSION = "m161.system_backup.v1"
BROWSER_CERT_VERSION = "m165.private_alpha.browser.v1"
CONFIG_SCHEMA_VERSION = "m160.alpha_config.v1"

# Primary certified machine class (do not claim broader support without evidence)
SUPPORTED_OS = "macOS"
SUPPORTED_ARCH = "arm64"
SUPPORTED_PYTHON = ("3.11", "3.12")
SUPPORTED_NODE_MIN = "18"
RECOMMENDED_MEMORY_GB = 8
REQUIRED_DISK_HEADROOM_GB = 5
REQUIRED_PORTS = {"backend": 8765, "frontend": 3000}
REQUIRED_DIRS = (
    "data/platform",
    "data/backups",
    "data/alpha",
    "data/alpha/config",
    "data/alpha/support",
    "data/alpha/restore",
)

KNOWN_LIMITATIONS = [
    "local-only single-machine private alpha",
    "not production-authorized",
    "public exposure not authorized",
    "no live payments",
    "no production Firebase",
    "no paid AI provider activation in first-run",
    "automations disabled by default; opt-in only",
    "Trading Guardian advisory / unengaged for private alpha",
    "no multi-host / multi-device sync",
    "no public marketplace",
    "owner-managed backups",
    "no guaranteed uptime",
    "synthetic/demo data for certification",
]


def _git_sha(full: bool = True) -> str:
    try:
        args = ["git", "rev-parse", "HEAD" if full else "--short", "HEAD"]
        if not full:
            args = ["git", "rev-parse", "--short", "HEAD"]
        out = subprocess.run(
            args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (out.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (out.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _pkg_versions() -> dict[str, str]:
    apps = {}
    packages = ROOT / "saathi" / "platform" / "apps" / "packages"
    if packages.is_dir():
        for child in packages.iterdir():
            app_json = child / "app.json"
            if app_json.is_file():
                try:
                    import json

                    data = json.loads(app_json.read_text(encoding="utf-8"))
                    aid = data.get("app_id") or data.get("id") or child.name
                    apps[str(aid)] = str(data.get("version") or "0.0.0")
                except Exception:
                    apps[child.name] = "unknown"
    return apps


def build_release_manifest(*, git_sha: str | None = None) -> dict[str, Any]:
    """Versioned private-alpha release definition (secret-free)."""
    sha = git_sha or _git_sha(full=True)
    py = platform.python_version()
    node = "unknown"
    try:
        node = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
    except Exception:
        pass
    npm = "unknown"
    try:
        npm = subprocess.run(
            ["npm", "--version"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
    except Exception:
        pass

    return {
        "schema": SCHEMA_VERSION,
        "saathios_release_version": RELEASE_VERSION,
        "git_sha": sha,
        "git_branch": _git_branch(),
        "schema_version": SCHEMA_VERSION,
        "platform_version": PLATFORM_VERSION,
        "application_package_versions": _pkg_versions(),
        "supported_operating_system": SUPPORTED_OS,
        "supported_cpu_architecture": SUPPORTED_ARCH,
        "supported_python_versions": list(SUPPORTED_PYTHON),
        "supported_node_min": SUPPORTED_NODE_MIN,
        "supported_package_managers": {"pip": "venv", "npm": ">=9"},
        "required_local_ports": dict(REQUIRED_PORTS),
        "required_directories": list(REQUIRED_DIRS),
        "required_disk_headroom_gb": REQUIRED_DISK_HEADROOM_GB,
        "recommended_memory_gb": RECOMMENDED_MEMORY_GB,
        "database_location": "data/platform/platform.db",
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "browser_certification_version": BROWSER_CERT_VERSION,
        "config_schema_version": CONFIG_SCHEMA_VERSION,
        "runtime_observed": {
            "python": py,
            "node": node,
            "npm": npm,
            "os": platform.system(),
            "arch": platform.machine(),
            "platform": platform.platform(),
        },
        "known_limitations": list(KNOWN_LIMITATIONS),
        "production_authorized": False,
        "public_exposure_authorized": False,
        "financial_execution_authorized": False,
        "paid_providers_authorized": False,
        "trading_live_authorized": False,
        "generated_at": time.time(),
        "channel": "private-alpha",
    }


def compatibility_matrix() -> dict[str, Any]:
    """Private-alpha capability compatibility matrix (evidence-backed claims)."""
    # Status vocabulary: CERTIFIED | CERTIFIED_WITH_LIMITATIONS | ADVISORY | NOT_CLAIMED
    cells = {
        "clean_setup": "CERTIFIED_WITH_LIMITATIONS",
        "existing_setup": "CERTIFIED_WITH_LIMITATIONS",
        "restart": "CERTIFIED",
        "upgrade": "CERTIFIED_WITH_LIMITATIONS",  # synthetic/local fixtures only
        "backup": "CERTIFIED",
        "restore": "CERTIFIED_WITH_LIMITATIONS",  # isolated/dry-run primary; destructive gated
        "browser_launch": "CERTIFIED_WITH_LIMITATIONS",
        "hcg": "CERTIFIED_WITH_LIMITATIONS",
        "ieltsalert": "CERTIFIED_WITH_LIMITATIONS",
        "unified_yeti": "CERTIFIED_WITH_LIMITATIONS",
        "universal_search": "CERTIFIED",
        "mission_runtime": "CERTIFIED_WITH_LIMITATIONS",
        "approval_center": "CERTIFIED",
        "execution_gateway": "CERTIFIED",
        "evidence": "CERTIFIED",
        "audit": "CERTIFIED",
        "automations_dry_run": "CERTIFIED",
        "automations_bounded_execution": "CERTIFIED_WITH_LIMITATIONS",
        "support_bundle": "CERTIFIED",
        "multi_host": "NOT_CLAIMED",
        "public_saas": "NOT_CLAIMED",
        "production": "NOT_CLAIMED",
    }
    return {
        "schema": "m157.compatibility.v1",
        "release_version": RELEASE_VERSION,
        "primary_machine": {
            "cpu": "Apple Silicon",
            "os": "macOS",
            "ram_gb": 8,
            "storage_class_gb": 256,
            "network": "localhost-only",
        },
        "matrix": cells,
        "notes": [
            "Broader OS/arch compatibility is NOT claimed without evidence.",
            "Upgrade certification is limited to synthetic/local release fixtures.",
            "Destructive restore requires owner/admin approval.",
        ],
    }


def write_manifest(path: Path | None = None) -> Path:
    dest = path or (ROOT / "data" / "alpha" / "release_manifest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    import json

    dest.write_text(json.dumps(build_release_manifest(), indent=2) + "\n", encoding="utf-8")
    return dest
