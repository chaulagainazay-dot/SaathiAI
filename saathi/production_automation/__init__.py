"""Production Automation Department — Credit Manager + Provider Scheduler + Character
Verification + Quality Gate + Retry, emitting a Production Plan. Saathi decides which
provider generates each scene using the credits available that day; generation calls
live behind adapters (deferred). Lets content be prepared/verified/queued while the
CEO runs the cafeteria.
"""
from saathi.production_automation.credits import CreditManager, default_manager
from saathi.production_automation.scheduler import assign_scenes, fallback_chain, retry_plan
from saathi.production_automation.quality import verify_scene, verify_package, quality_gate
from saathi.production_automation.pipeline import build_plan, ProductionStore, default_store, APPROVAL_MODES

__all__ = ["CreditManager", "default_manager", "assign_scenes", "fallback_chain", "retry_plan",
           "verify_scene", "verify_package", "quality_gate", "build_plan", "ProductionStore",
           "default_store", "APPROVAL_MODES"]
