"""M157–M165 SaathiOS Private Alpha release engineering package.

Composition-only release layer over certified SaathiOS Core services.
Does NOT introduce a second runtime, scheduler, backup engine, monitoring
platform, authentication system, or ExecutionGateway.

Authority:
- Lifecycle: bin/saathi-local (ownership-safe, localhost-only)
- Persistence: PlatformStore
- Execution: Mission Runtime → Agent Runtime → ExecutionGateway → Approval Center
- Backup substrate: saathi.ops.backup patterns + platform.db full-system pack
- Health: M55 ReleaseOperationsService + M57 local_readiness

production_authorized: false
public_exposure_authorized: false
"""
from __future__ import annotations

from .manifest import (
    RELEASE_VERSION,
    build_release_manifest,
    compatibility_matrix,
)
from .config import (
    AlphaConfig,
    load_config,
    save_config,
    validate_config,
    migrate_config,
    rollback_config,
    config_diff,
)
from .prepare import prepare, doctor, init_first_run, open_entry
from .backup_restore import (
    create_system_backup,
    restore_system_backup,
    verify_system_backup,
    dry_run_restore,
    list_system_backups,
    prune_system_backups,
    disaster_recovery_drill,
)
from .automations import AutomationExecutionService
from .support import export_support_bundle
from .certification import run_private_alpha_certification
from .incidents import INCIDENT_PLAYBOOKS, playbook_for
from .upgrade import upgrade_preflight, apply_local_upgrade, rollback_upgrade
from .operator_validation import run_synthetic_operator_validation

__all__ = [
    "RELEASE_VERSION",
    "build_release_manifest",
    "compatibility_matrix",
    "AlphaConfig",
    "load_config",
    "save_config",
    "validate_config",
    "migrate_config",
    "rollback_config",
    "config_diff",
    "prepare",
    "doctor",
    "init_first_run",
    "open_entry",
    "create_system_backup",
    "restore_system_backup",
    "verify_system_backup",
    "dry_run_restore",
    "list_system_backups",
    "prune_system_backups",
    "disaster_recovery_drill",
    "AutomationExecutionService",
    "export_support_bundle",
    "run_private_alpha_certification",
    "INCIDENT_PLAYBOOKS",
    "playbook_for",
    "upgrade_preflight",
    "apply_local_upgrade",
    "rollback_upgrade",
    "run_synthetic_operator_validation",
]
