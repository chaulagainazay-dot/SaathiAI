"""T-NEXT-4 Phase 4 — idempotent submission and retry disposition.

Invariant tests written BEFORE implementation (TDD).

The central rule under test: an UNKNOWN submission outcome must never be
automatically retried. It must route to reconciliation. Getting this wrong is
how a paper system that later gains a broker double-submits real capital.
"""
from __future__ import annotations

import pytest

from saathi.platform.paper_trading.execution_integrity import (
    RetryDisposition,
    SubmissionAttemptStore,
    SubmissionOutcome,
    classify_submission,
)


# ── disposition mapping ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "outcome,expected",
    [
        (SubmissionOutcome.ACKNOWLEDGED, RetryDisposition.DO_NOT_RETRY),
        (SubmissionOutcome.REJECTED, RetryDisposition.DO_NOT_RETRY),
        (SubmissionOutcome.TIMEOUT_BEFORE_SEND, RetryDisposition.SAFE_TO_RETRY),
        (SubmissionOutcome.TIMEOUT_AFTER_SEND, RetryDisposition.RECONCILE_FIRST),
        (SubmissionOutcome.CONNECTION_LOST, RetryDisposition.RECONCILE_FIRST),
        (SubmissionOutcome.UNKNOWN, RetryDisposition.RECONCILE_FIRST),
    ],
)
def test_disposition_mapping_is_deterministic(outcome, expected):
    assert classify_submission(outcome) is expected
    # deterministic: same input, same output, no clock or randomness
    assert classify_submission(outcome) is classify_submission(outcome)


def test_unknown_is_never_safe_to_retry():
    """The mission's hard rule. UNKNOWN must never auto-retry."""
    for outcome in SubmissionOutcome:
        disposition = classify_submission(outcome)
        if outcome in (
            SubmissionOutcome.UNKNOWN,
            SubmissionOutcome.TIMEOUT_AFTER_SEND,
            SubmissionOutcome.CONNECTION_LOST,
        ):
            assert disposition is not RetryDisposition.SAFE_TO_RETRY


def test_only_definitely_untransmitted_is_safe_to_retry():
    safe = [o for o in SubmissionOutcome if classify_submission(o) is RetryDisposition.SAFE_TO_RETRY]
    assert safe == [SubmissionOutcome.TIMEOUT_BEFORE_SEND]


def test_unrecognised_outcome_fails_closed():
    """An outcome the classifier does not know must not be retryable."""
    assert classify_submission("some-future-outcome") is RetryDisposition.RECONCILE_FIRST
    assert classify_submission(None) is RetryDisposition.RECONCILE_FIRST


# ── attempt ledger ─────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    return SubmissionAttemptStore(tmp_path / "attempts.db")


def _record(store, *, attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED, key="idem-1"):
    return store.record(
        request_id=f"req-{attempt}",
        client_order_id="coid-1",
        idempotency_key=key,
        attempt=attempt,
        outcome=outcome,
        broker_adapter_ref="paper:v1",
        correlation_id="corr-1",
        evidence_ref="ev-1",
    )


def test_attempt_is_persisted_durably(store, tmp_path):
    _record(store)
    reopened = SubmissionAttemptStore(tmp_path / "attempts.db")
    attempts = reopened.attempts_for("idem-1")
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == SubmissionOutcome.ACKNOWLEDGED.value
    assert attempts[0]["disposition"] == RetryDisposition.DO_NOT_RETRY.value


def test_same_idempotency_key_cannot_submit_twice(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.ACKNOWLEDGED)
    assert store.already_submitted("idem-1") is True
    assert store.may_submit("idem-1") is False


def test_key_with_no_attempts_may_submit(store):
    assert store.may_submit("never-seen") is True
    assert store.already_submitted("never-seen") is False


def test_safe_to_retry_outcome_permits_resubmission(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.TIMEOUT_BEFORE_SEND)
    assert store.may_submit("idem-1") is True
    assert store.already_submitted("idem-1") is False


def test_reconcile_first_outcome_blocks_resubmission(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.TIMEOUT_AFTER_SEND)
    assert store.may_submit("idem-1") is False
    assert store.requires_reconciliation("idem-1") is True


def test_unknown_outcome_blocks_and_requires_reconciliation(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.UNKNOWN)
    assert store.may_submit("idem-1") is False
    assert store.requires_reconciliation("idem-1") is True


def test_rejected_is_terminal_and_not_retryable(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.REJECTED)
    assert store.may_submit("idem-1") is False
    assert store.requires_reconciliation("idem-1") is False


def test_duplicate_request_id_is_idempotent(store):
    first = _record(store, attempt=1)
    second = _record(store, attempt=1)
    assert first["request_id"] == second["request_id"]
    assert len(store.attempts_for("idem-1")) == 1


def test_reconciliation_clearance_unblocks_only_when_not_transmitted(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.UNKNOWN)
    assert store.may_submit("idem-1") is False

    store.record_reconciliation(
        idempotency_key="idem-1",
        external_order_found=False,
        resolved_outcome=SubmissionOutcome.TIMEOUT_BEFORE_SEND,
        evidence_ref="recon-1",
    )
    assert store.may_submit("idem-1") is True


def test_reconciliation_finding_external_order_keeps_submission_blocked(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.UNKNOWN)
    store.record_reconciliation(
        idempotency_key="idem-1",
        external_order_found=True,
        resolved_outcome=SubmissionOutcome.ACKNOWLEDGED,
        evidence_ref="recon-2",
    )
    assert store.may_submit("idem-1") is False
    assert store.already_submitted("idem-1") is True


def test_attempt_history_is_append_only(store):
    _record(store, attempt=1, outcome=SubmissionOutcome.TIMEOUT_BEFORE_SEND)
    _record(store, attempt=2, outcome=SubmissionOutcome.ACKNOWLEDGED)
    attempts = store.attempts_for("idem-1")
    assert [a["attempt"] for a in attempts] == [1, 2]
    # the earlier attempt is preserved verbatim, not overwritten
    assert attempts[0]["outcome"] == SubmissionOutcome.TIMEOUT_BEFORE_SEND.value


def test_every_attempt_carries_full_provenance(store):
    _record(store)
    a = store.attempts_for("idem-1")[0]
    for field in (
        "request_id", "client_order_id", "idempotency_key", "attempt",
        "outcome", "disposition", "broker_adapter_ref", "correlation_id",
        "evidence_ref", "recorded_at",
    ):
        assert field in a, f"missing provenance field: {field}"


# ── regressions for defects found by fresh-context review ──────────────────

def test_reconciliation_row_without_attempt_row_still_blocks(store):
    """R1: may_submit must consult the reconciliation table even when no attempt
    row exists for the key. Short-circuiting on an empty attempt list would
    permit a duplicate against an order we know reached the venue."""
    store.record_reconciliation(
        idempotency_key="orphan-key",
        external_order_found=True,
        resolved_outcome=SubmissionOutcome.ACKNOWLEDGED,
        evidence_ref="recon-orphan",
    )
    assert store.already_submitted("orphan-key") is True
    assert store.may_submit("orphan-key") is False


def test_record_is_idempotent_under_concurrent_same_request_id(store):
    """R3: record() must not raise IntegrityError on a duplicate request_id."""
    a = _record(store, attempt=1)
    b = _record(store, attempt=1)
    c = _record(store, attempt=1)
    assert a["request_id"] == b["request_id"] == c["request_id"]
    assert len(store.attempts_for("idem-1")) == 1
