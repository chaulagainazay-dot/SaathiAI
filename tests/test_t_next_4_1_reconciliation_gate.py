"""T-NEXT-4.1 enforcement tests.

These tests specify the gate at the canonical PaperTradingService boundary.
They intentionally use a deterministic authority double so the service wiring
is tested independently from snapshot construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.paper_trading import MarketEvent, PaperStore, PaperTradingService
from saathi.platform.paper_trading.execution_integrity import (
    ExecutionReadiness,
    ReconciliationVerdict,
    SubmissionAttemptStore,
    SubmissionOutcome,
    RetryDisposition,
)
from saathi.platform.trading_models import D, DataQuality, MarketState


def _ctx():
    return PlatformExecutionContext(user_id="u1", role="operator", org_id="o1", workspace_id="w1", run_id="r1")


def _event():
    return MarketEvent(
        symbol="AAPL", ts=1000.0, bid=D("99.9"), ask=D("100.1"), last=D("100"),
        liquidity=D("10000"), quality=DataQuality.VALID, market_state=MarketState.OPEN, ref="test",
    )


@dataclass
class _Authority:
    readiness: ExecutionReadiness

    def evaluate(self, **_kwargs):
        return ReconciliationVerdict(self.readiness, self.readiness is ExecutionReadiness.RECONCILED)


def _service(tmp_path, readiness=ExecutionReadiness.RECONCILED):
    store = PaperStore(tmp_path / "paper.db")
    svc = PaperTradingService(store, reconciliation_authority=_Authority(readiness))
    acct = svc.create_account(_ctx(), name="paper", starting_cash="100000")
    intent = svc.create_intent(
        _ctx(), account_id=acct["id"], symbol="AAPL", side="BUY", order_type="MARKET", quantity="1",
    )
    return svc, intent


@pytest.mark.parametrize("readiness", [
    ExecutionReadiness.MISMATCH,
    ExecutionReadiness.UNKNOWN,
    ExecutionReadiness.DATA_INSUFFICIENT,
    ExecutionReadiness.TEMPORARILY_PENDING,
])
def test_non_reconciled_states_block_before_order_write(tmp_path, readiness):
    svc, intent = _service(tmp_path, readiness)
    with pytest.raises(PlatformContextError) as exc:
        svc.submit_order(_ctx(), intent_id=intent["intent_id"], event=_event())
    assert exc.value.code == "RECONCILIATION_REQUIRED"
    assert svc.store.list_orders("o1") == []


def test_reconciled_state_proceeds(tmp_path):
    svc, intent = _service(tmp_path)
    out = svc.submit_order(_ctx(), intent_id=intent["intent_id"], event=_event())
    assert out["order"]["broker_state"] == "OPEN"


def test_attempt_store_disposition_is_fail_closed(tmp_path):
    attempts = SubmissionAttemptStore(tmp_path / "attempts.db")
    for outcome, expected in (
        (SubmissionOutcome.ACKNOWLEDGED, RetryDisposition.DO_NOT_RETRY),
        (SubmissionOutcome.REJECTED, RetryDisposition.DO_NOT_RETRY),
        (SubmissionOutcome.TIMEOUT_AFTER_SEND, RetryDisposition.RECONCILE_FIRST),
        (SubmissionOutcome.CONNECTION_LOST, RetryDisposition.RECONCILE_FIRST),
        (SubmissionOutcome.UNKNOWN, RetryDisposition.RECONCILE_FIRST),
    ):
        row = attempts.record(
            request_id=f"r-{outcome.value}", client_order_id="c", idempotency_key=outcome.value,
            attempt=1, outcome=outcome,
        )
        assert row["disposition"] == expected.value
        assert attempts.may_submit(outcome.value) is False


def test_only_timeout_before_send_is_retryable(tmp_path):
    attempts = SubmissionAttemptStore(tmp_path / "attempts.db")
    attempts.record(request_id="r", client_order_id="c", idempotency_key="k", attempt=1,
                    outcome=SubmissionOutcome.TIMEOUT_BEFORE_SEND)
    assert attempts.may_submit("k") is True


@pytest.mark.parametrize("outcome", [
    SubmissionOutcome.TIMEOUT_AFTER_SEND,
    SubmissionOutcome.CONNECTION_LOST,
    SubmissionOutcome.UNKNOWN,
])
def test_ambiguous_attempt_blocks_new_service_execution(tmp_path, outcome):
    attempts = SubmissionAttemptStore(tmp_path / "attempts.db")
    attempts.record(request_id="r", client_order_id="c", idempotency_key="k", attempt=1, outcome=outcome)
    svc, intent = _service(tmp_path)
    # Replace the service's clean store with the intentionally ambiguous one.
    svc.submission_attempts.close()
    svc.submission_attempts = attempts
    # Refreshing startup state must discover the ambiguity before order writes.
    with pytest.raises(PlatformContextError, match="startup execution ambiguity"):
        svc.submit_order(_ctx(), intent_id=intent["intent_id"], event=_event())


def test_attempt_intent_is_finalized_as_acknowledged(tmp_path):
    svc, intent = _service(tmp_path)
    svc.submit_order(_ctx(), intent_id=intent["intent_id"], event=_event())
    rows = svc.submission_attempts.attempts_for(intent["idempotency_key"])
    assert len(rows) == 1
    assert rows[0]["outcome"] == SubmissionOutcome.ACKNOWLEDGED.value


def test_replace_is_explicitly_unsupported(tmp_path):
    svc, _ = _service(tmp_path)
    with pytest.raises(PlatformContextError) as exc:
        svc.replace_order(_ctx(), order_id="o1")
    assert exc.value.code == "REPLACE_UNSUPPORTED"


def test_duplicate_request_record_is_idempotent_under_concurrency(tmp_path):
    attempts = SubmissionAttemptStore(tmp_path / "attempts.db")
    def record():
        return attempts.record(request_id="same", client_order_id="c", idempotency_key="k",
                               attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED)
    with ThreadPoolExecutor(max_workers=10) as pool:
        rows = list(pool.map(lambda _n: record(), range(10)))
    assert {r["request_id"] for r in rows} == {"same"}
    assert len(attempts.attempts_for("k")) == 1


def test_future_outcome_fails_closed():
    from saathi.platform.paper_trading.execution_integrity import classify_submission
    assert classify_submission("FUTURE_VALUE").value == "RECONCILE_FIRST"


def test_unknown_external_state_is_not_masked_by_healthy_oms(tmp_path):
    from saathi.platform.paper_trading.execution_integrity import (
        ExternalOrderSnapshot, LedgerSnapshot, OmsSnapshot, ReconciliationAuthority,
    )
    order = {"order_id": "o", "state": "OPEN", "filled_quantity": "0"}
    unknown = {"order_id": "o", "state": "UNKNOWN", "filled_quantity": "0"}
    verdict = ReconciliationAuthority().evaluate(
        oms=OmsSnapshot([order], [], 1), external=ExternalOrderSnapshot([unknown], [], 1),
        ledger=LedgerSnapshot("100", {}, 1), expected_cash="100", expected_positions={},
    )
    assert verdict.readiness is ExecutionReadiness.UNKNOWN
    assert verdict.permits_new_execution is False
