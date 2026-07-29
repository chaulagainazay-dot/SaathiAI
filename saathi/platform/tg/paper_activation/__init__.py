"""M192–M199 — Paper Activation Governance.

Owner-approved PAPER_ELIGIBLE strategies only may become PAPER_ACTIVE
and trade inside a deterministic paper portfolio.

No live broker. No exchange credentials. No production deploy.
"""
from saathi.platform.tg.paper_activation.models import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    PaperActivationState,
    ActivationApprovalStatus,
    PortfolioStatus,
    RiskHaltReason,
    RiskLimits,
)
from saathi.platform.tg.paper_activation.service import (
    PaperActivationGovernanceService,
    default_paper_gov,
    reset_paper_gov_for_tests,
    PaperGovError,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "PaperActivationState",
    "ActivationApprovalStatus",
    "PortfolioStatus",
    "RiskHaltReason",
    "RiskLimits",
    "PaperActivationGovernanceService",
    "default_paper_gov",
    "reset_paper_gov_for_tests",
    "PaperGovError",
]
