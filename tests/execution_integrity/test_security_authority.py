"""T-NEXT-4 Phase 15 — authority boundary tests.

These are the tests that make the certification meaningful. Each asserts a
property about *who is allowed to cause an external action*, not about whether
some code path happens to work.
"""
from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from saathi.platform.paper_trading import execution_integrity as ei

REPO = Path(__file__).resolve().parents[2]
EXECUTION_PLANE = [
    REPO / "saathi" / "platform" / "paper_trading",
    REPO / "saathi" / "execution",
    REPO / "saathi" / "platform" / "fund_ledger",
    REPO / "saathi" / "platform" / "portfolio_construction",
]


def _grep(pattern: str, paths) -> list[str]:
    cmd = ["grep", "-rIn", "-E", pattern, *[str(p) for p in paths if p.exists()]]
    out = subprocess.run(cmd, capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if "/__pycache__/" not in line]


# ── no TradingAgents anywhere in the execution plane ────────────────────────

def test_no_tradingagents_code_in_execution_plane():
    hits = _grep(r"\btradingagents\b|TauricResearch", EXECUTION_PLANE)
    assert hits == [], f"TradingAgents reference in execution plane: {hits}"


def test_no_langgraph_or_backtrader_dependency_in_execution_plane():
    hits = _grep(r"import +(langgraph|backtrader)|from +(langgraph|backtrader)", EXECUTION_PLANE)
    assert hits == [], f"forbidden dependency in execution plane: {hits}"


# ── no LLM in the execution plane ───────────────────────────────────────────

def test_execution_integrity_module_has_no_llm_dependency():
    """No import line in the integrity module may reach an LLM surface."""
    src = Path(ei.__file__).read_text(encoding="utf-8")
    import_lines = [
        ln for ln in src.splitlines()
        if ln.startswith("import ") or ln.startswith("from ")
    ]
    forbidden = ("openai", "anthropic", "model_router", "saathi.inference", "langchain", "llm")
    offenders = [
        ln for ln in import_lines
        if any(f in ln.lower() for f in forbidden)
    ]
    assert offenders == [], f"LLM surface imported by integrity module: {offenders}"


def test_no_llm_inference_import_in_paper_trading_execution_path():
    hits = _grep(
        r"from +saathi\.inference|import +saathi\.inference|from +saathi\.model_router|import +saathi\.model_router",
        [REPO / "saathi" / "platform" / "paper_trading"],
    )
    assert hits == [], f"LLM inference reachable from paper trading execution path: {hits}"


# ── ReconciliationAuthority holds no execution authority ────────────────────

def test_reconciliation_authority_exposes_no_execution_verbs():
    forbidden = {
        "approve", "authorize", "authorise", "submit", "execute", "place_order",
        "cancel", "send", "trade", "override", "force",
    }
    names = {n for n, _ in inspect.getmembers(ei.ReconciliationAuthority) if not n.startswith("_")}
    assert not (names & forbidden), f"authority exposes execution verbs: {names & forbidden}"


def test_reconciliation_verdict_exposes_no_execution_verbs():
    forbidden = {"approve", "authorize", "authorise", "submit", "execute", "override"}
    names = {n for n, _ in inspect.getmembers(ei.ReconciliationVerdict) if not n.startswith("_")}
    assert not (names & forbidden)


def test_reconciliation_authority_cannot_mutate_a_ledger():
    src = Path(ei.__file__).read_text(encoding="utf-8")
    for forbidden in ("record_fill", "post_accepted_fill", "PortfolioLedgerService", "record_deposit"):
        assert forbidden not in src, f"authority reaches ledger mutation: {forbidden}"


# ── only RECONCILED permits execution ───────────────────────────────────────

def test_no_readiness_other_than_reconciled_permits_execution():
    for readiness in ei.ExecutionReadiness:
        permitted = ei.readiness_permits(readiness, allow_execution_while_pending=False)
        assert permitted is (readiness is ei.ExecutionReadiness.RECONCILED)


def test_unknown_blocks_execution():
    assert ei.readiness_permits(ei.ExecutionReadiness.UNKNOWN) is False
    assert ei.readiness_permits(ei.ExecutionReadiness.UNKNOWN, allow_execution_while_pending=True) is False


def test_mismatch_blocks_execution():
    assert ei.readiness_permits(ei.ExecutionReadiness.MISMATCH) is False
    assert ei.readiness_permits(ei.ExecutionReadiness.MISMATCH, allow_execution_while_pending=True) is False


def test_data_insufficient_blocks_execution():
    assert ei.readiness_permits(ei.ExecutionReadiness.DATA_INSUFFICIENT) is False
    assert ei.readiness_permits(ei.ExecutionReadiness.DATA_INSUFFICIENT, allow_execution_while_pending=True) is False


# ── submission disposition cannot be widened accidentally ───────────────────

def test_no_ambiguous_outcome_is_ever_safe_to_retry():
    ambiguous = {
        ei.SubmissionOutcome.UNKNOWN,
        ei.SubmissionOutcome.TIMEOUT_AFTER_SEND,
        ei.SubmissionOutcome.CONNECTION_LOST,
    }
    for outcome in ambiguous:
        assert ei.classify_submission(outcome) is not ei.RetryDisposition.SAFE_TO_RETRY


def test_unrecognised_outcome_fails_closed():
    for bogus in ("", "MAYBE", "OK", None, 0, object()):
        assert ei.classify_submission(bogus) is ei.RetryDisposition.RECONCILE_FIRST


# ── paper-only guarantees ───────────────────────────────────────────────────

def test_paper_safety_rejects_live_configuration():
    from saathi.platform.paper_trading import PaperSafetyError, assert_paper_safe
    for token in ("LIVE", "PRODUCTION", "REAL_MONEY", "LEVERAGE", "MARGIN", "SHORT_SELLING"):
        with pytest.raises(PaperSafetyError):
            assert_paper_safe({token.lower(): True})


def test_no_real_broker_sdk_in_execution_plane():
    hits = _grep(
        r"import +(alpaca|ib_insync|ibapi|ccxt|binance|kite|robinhood|tda|schwab|oanda)",
        EXECUTION_PLANE,
    )
    assert hits == [], f"real broker SDK present: {hits}"


def test_no_withdrawal_authority_in_execution_plane():
    hits = _grep(r"def +(withdraw|transfer_out|payout)\b", EXECUTION_PLANE)
    real = [h for h in hits if "_sim" not in h and "simulat" not in h.lower()]
    assert real == [], f"withdrawal authority present: {real}"


def test_no_network_egress_in_execution_integrity_module():
    src = Path(ei.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests.", "httpx", "urllib", "socket", "aiohttp", "fetch("):
        assert forbidden not in src, f"network egress in integrity module: {forbidden}"


# ── determinism ─────────────────────────────────────────────────────────────

def test_authority_verdict_is_deterministic_for_identical_input():
    authority = ei.ReconciliationAuthority(clock=lambda: 42.0)
    order = {"order_id": "o1", "client_order_id": "c1", "state": "FILLED", "filled_quantity": "10"}
    kwargs = dict(
        oms=ei.OmsSnapshot(orders=[order], fills=[], as_of=1.0),
        external=ei.ExternalOrderSnapshot(orders=[], fills=[], as_of=1.0),
        ledger=ei.LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00",
        expected_positions={},
    )
    a = authority.evaluate(**kwargs)
    b = authority.evaluate(**kwargs)
    assert a.to_dict() == b.to_dict()


def test_no_randomness_in_integrity_module():
    src = Path(ei.__file__).read_text(encoding="utf-8")
    for forbidden in ("import random", "uuid4", "secrets."):
        assert forbidden not in src, f"non-determinism in integrity module: {forbidden}"
