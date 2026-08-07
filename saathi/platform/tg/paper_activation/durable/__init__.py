"""M200–M207 Durable multi-process paper ledger and long-horizon operations."""
from saathi.platform.tg.paper_activation.durable.schema import SCHEMA_VERSION, ENGINE_VERSION
from saathi.platform.tg.paper_activation.durable.store import DurablePaperStore
from saathi.platform.tg.paper_activation.durable.service import (
    DurablePaperGovernanceService,
    default_durable_gov,
    reset_durable_gov_for_tests,
    DurableGovError,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "DurablePaperStore",
    "DurablePaperGovernanceService",
    "default_durable_gov",
    "reset_durable_gov_for_tests",
    "DurableGovError",
]
