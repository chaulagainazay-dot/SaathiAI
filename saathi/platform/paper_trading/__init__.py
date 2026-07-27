"""M62.5 — deterministic, durable paper-trading broker and order lifecycle.

Simulation only. A paper fill is NOT a live trade, recommendation, or authorization
to allocate capital. No live broker, real money, leverage, margin, short-selling,
options, futures, perpetuals, derivatives, borrowing, or network access exists here.
PAPER environment only; long-only. Mutations flow exclusively through the registered
paper-trading tool under ExecutionGateway.
"""
from saathi.platform.paper_trading.models import (
    PaperAccount, PaperPosition, PaperOrder, PaperFill, AccountStatus, BrokerOrderState,
    FeeModel, SlippageModel, ZERO_FEE, REALISTIC_FEE, ZERO_SLIP, REALISTIC_SLIP,
    assert_paper_safe, PaperSafetyError, PROHIBITED_CONFIG_TOKENS, ENGINE_VERSION,
    can_account_transition, can_broker_transition, q2, q6,
)
from saathi.platform.paper_trading.broker import PaperBroker, MarketEvent, FillPlan, ValidationResult, from_quote, from_bar
from saathi.platform.paper_trading.store import PaperStore, IdempotencyConflict
from saathi.platform.paper_trading.service import PaperTradingService, APPROVAL_NOTIONAL_THRESHOLD
from saathi.platform.paper_trading import orchestration
from saathi.platform.paper_trading.execution_tool import (
    register_paper_tools, paper_trading_manifests, default_paper_service, set_paper_service_for_tests,
)
from saathi.platform.paper_trading import fixtures

__all__ = [
    "PaperAccount", "PaperPosition", "PaperOrder", "PaperFill", "AccountStatus", "BrokerOrderState",
    "FeeModel", "SlippageModel", "ZERO_FEE", "REALISTIC_FEE", "ZERO_SLIP", "REALISTIC_SLIP",
    "assert_paper_safe", "PaperSafetyError", "PROHIBITED_CONFIG_TOKENS", "ENGINE_VERSION",
    "can_account_transition", "can_broker_transition", "q2", "q6",
    "PaperBroker", "MarketEvent", "FillPlan", "ValidationResult", "from_quote", "from_bar",
    "PaperStore", "IdempotencyConflict", "PaperTradingService", "APPROVAL_NOTIONAL_THRESHOLD",
    "orchestration", "register_paper_tools", "paper_trading_manifests", "default_paper_service",
    "set_paper_service_for_tests", "fixtures",
]
