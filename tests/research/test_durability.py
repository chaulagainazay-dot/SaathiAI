"""RESEARCH-3-PERSISTENCE durable audit and restart-safety tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

import pytest

from saathi.platform.market_data.contract import AssetClass
from saathi.platform.portfolio_construction.models import (
    CandidatePortfolio,
    CandidatePortfolioStatus,
    InstrumentAllocation,
    StrategyQualificationEvidence,
    StrategyQualificationStatus,
)
from saathi.platform.research.durability import (
    DURABILITY_SCHEMA_VERSION,
    PersistenceBusyError,
    PersistenceConflictError,
    PersistenceCorruptError,
    ResearchDurabilityStore,
    UnsupportedSchemaVersion,
)
from saathi.platform.research.journal import (
    DecisionJournal,
    DecisionOutcome,
    InvestmentDecisionRecord,
    InvestmentLesson,
    LessonStatus,
)
from saathi.platform.research.store import ResearchStore
from saathi.platform.signal import Direction, TradingIntentProposal, TradingSignal


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"


def _decision(decision_id: str = "decision-1") -> InvestmentDecisionRecord:
    return InvestmentDecisionRecord(
        decision_id,
        BTC,
        NOW,
        "thesis-1",
        "RESEARCH_ONLY",
        "LONG",
        "30d",
        research_run_id="research-run-1",
        research_snapshot_id="research-snapshot-1",
        assumptions=("public spot data remains representative",),
        invalidation_conditions=("qualification revoked",),
        available_at=NOW,
        valid_until=NOW + timedelta(days=1),
    )


def _outcome(revision: int = 1) -> DecisionOutcome:
    return DecisionOutcome(
        "outcome-1",
        "decision-1",
        NOW,
        NOW + timedelta(days=30 * revision),
        Decimal("0.10") + Decimal(revision - 1) / Decimal("100"),
        Decimal("0.08"),
        revision=revision,
        available_at=NOW + timedelta(days=30 * revision),
    )


def _lesson(
    *, status: LessonStatus = LessonStatus.OBSERVED, version: int = 1, sample_size: int = 1
) -> InvestmentLesson:
    return InvestmentLesson(
        "lesson-1",
        ("decision-1",),
        "bounded evidence should remain proposal-only",
        "AUTHORITY",
        "INSTRUMENT",
        BTC,
        NOW,
        NOW + timedelta(days=365),
        status=status,
        sample_size=sample_size,
        version=version,
    )


def _signal(*, valid_until: datetime | None = None) -> TradingSignal:
    return TradingSignal.create(
        "crypto_spot_mean_reversion",
        "1.0.0",
        BTC,
        Direction.LONG_BIAS,
        "0.5",
        NOW,
        valid_until or NOW + timedelta(hours=1),
        "HISTORICAL",
        ("FROZEN_STRATEGY_OUTPUT",),
    )


def _qualification(intent: TradingIntentProposal) -> StrategyQualificationEvidence:
    return StrategyQualificationEvidence(
        intent_id=intent.intent_id,
        signal_ref=intent.signal_refs[0],
        strategy_id="crypto_spot_mean_reversion",
        strategy_version="1.0.0",
        instrument_id=BTC,
        status=StrategyQualificationStatus.PAPER_CANDIDATE,
        qualification_artifact_sha256=(
            "45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40"
        ),
        dataset_version=(
            "sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8"
        ),
        selected_config_hash=(
            "8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72"
        ),
        quality="CERTIFIED_WITH_LIMITATIONS",
    )


def _candidate(intent: TradingIntentProposal) -> CandidatePortfolio:
    allocation = InstrumentAllocation(
        instrument_id=BTC,
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        quote_currency="USDT",
        current_weight=Decimal("0"),
        target_weight=Decimal("0.10"),
        weight_change=Decimal("0.10"),
        target_notional=Decimal("10000"),
        estimated_cost=Decimal("40"),
        strategy_ids=("crypto_spot_mean_reversion",),
        intent_ids=(intent.intent_id,),
    )
    return CandidatePortfolio(
        candidate_portfolio_id="candidate-1",
        request_id="construction-request-1",
        fund_id="fund-1",
        status=CandidatePortfolioStatus.CANDIDATE_ALLOCATION,
        portfolio_snapshot_ref="ledger-snapshot-1",
        market_data_snapshot_ref="market-snapshot-1",
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version="paper-risk-budget/v2-configured-conservative",
        decision_time=NOW,
        allocations=(allocation,),
        cash_current_weight=Decimal("1"),
        cash_target_weight=Decimal("0.90"),
        turnover=Decimal("0.10"),
        estimated_cost=Decimal("40"),
        rejected_intents=(),
        constraint_effects=(),
        reason_codes=(),
        intent_ids=(intent.intent_id,),
        strategy_ids=("crypto_spot_mean_reversion",),
        qualification_artifact_sha256=(
            "45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40",
        ),
        dataset_versions=(
            "sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8",
        ),
        selected_config_hashes=(
            "8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72",
        ),
        policy_assumption_status="CONFIGURED_POLICY_ASSUMPTION",
        quality="VALID_WITH_LIMITATIONS",
        market_data_mode="HISTORICAL",
    )


@pytest.fixture
def durable(tmp_path):
    base = ResearchStore(tmp_path / "platform.db")
    store = ResearchDurabilityStore(research_store=base)
    yield store
    store.close()


def test_reuses_existing_research_database_and_records_schema_version(tmp_path):
    path = tmp_path / "platform.db"
    base = ResearchStore(path)
    store = ResearchDurabilityStore(research_store=base)

    assert store.db_path == path
    assert store.schema_version == DURABILITY_SCHEMA_VERSION
    assert path.exists()
    store.close()


def test_decision_is_idempotent_restart_durable_and_conflicts_are_explicit(tmp_path):
    path = tmp_path / "platform.db"
    first = ResearchDurabilityStore(research_store=ResearchStore(path))
    decision = _decision()
    assert first.save_decision(decision) == "RECORDED"
    assert first.save_decision(decision) == "DUPLICATE"
    with pytest.raises(PersistenceConflictError):
        first.save_decision(replace(decision, thesis_id="different-thesis"))
    first.close()

    restarted = ResearchDurabilityStore(research_store=ResearchStore(path))
    assert restarted.get_decision(decision.decision_id) == decision
    restarted.close()


def test_decision_journal_can_use_durable_backend_without_in_memory_correctness(tmp_path):
    path = tmp_path / "platform.db"
    store = ResearchDurabilityStore(research_store=ResearchStore(path))
    journal = DecisionJournal(durability_store=store)
    assert journal.record(_decision()) == "RECORDED"
    assert journal.add_outcome(_outcome()) == "RECORDED"
    store.close()

    restarted = ResearchDurabilityStore(research_store=ResearchStore(path))
    recovered = DecisionJournal(durability_store=restarted)
    assert recovered.get_decision("decision-1") == _decision()
    assert recovered.list_outcome_revisions("outcome-1") == [_outcome()]
    restarted.close()


def test_outcome_revisions_append_without_erasing_prior_analysis(durable):
    durable.save_outcome(_outcome(1))
    durable.save_outcome(_outcome(2))

    revisions = durable.list_outcome_revisions("outcome-1")
    assert [x.revision for x in revisions] == [1, 2]
    assert revisions[0].observation_end < revisions[1].observation_end


def test_lesson_cannot_self_promote_and_revision_history_is_preserved(durable):
    assert durable.save_lesson(_lesson()) == "RECORDED"
    with pytest.raises(PermissionError, match="cannot self-promote"):
        durable.save_lesson(_lesson(status=LessonStatus.PROMOTED, version=2, sample_size=3))

    validating = durable.transition_lesson(
        "lesson-1", LessonStatus.VALIDATING, expected_version=1, sample_size=3
    )
    promoted = durable.transition_lesson(
        "lesson-1",
        LessonStatus.PROMOTED,
        expected_version=2,
        review_ref="deterministic-review-1",
    )
    assert validating.version == 2
    assert promoted.version == 3
    assert [x.status for x in durable.list_lesson_revisions("lesson-1")] == [
        LessonStatus.OBSERVED,
        LessonStatus.VALIDATING,
        LessonStatus.PROMOTED,
    ]


def test_signal_and_intent_restart_recovery_never_replays_or_executes(tmp_path):
    path = tmp_path / "platform.db"
    signal = _signal(valid_until=NOW + timedelta(minutes=1))
    intent = TradingIntentProposal.from_signal(signal)
    first = ResearchDurabilityStore(research_store=ResearchStore(path))
    first.save_signal(signal)
    first.save_intent(intent)
    first.close()

    restarted = ResearchDurabilityStore(research_store=ResearchStore(path))
    recovered = restarted.recover_non_authoritative_state(at=NOW + timedelta(days=1))
    assert recovered["signals"][0]["expired"] is True
    assert recovered["intents"][0]["expired"] is True
    assert recovered["replay_allowed"] is False
    assert recovered["authorizes_execution"] is False
    assert recovered["orders_created"] == 0
    assert recovered["signals"][0]["decision_time"] == NOW.isoformat()
    assert recovered["signals"][0]["available_at"] == NOW.isoformat()
    assert recovered["signals"][0]["generated_at"] == NOW.isoformat()
    assert recovered["intents"][0]["generated_at"] == NOW.isoformat()
    assert recovered["intents"][0]["data_mode"] == "HISTORICAL"
    restarted.close()


def test_qualification_and_construction_audit_preserve_immutable_refs(durable):
    signal = _signal()
    intent = TradingIntentProposal.from_signal(signal)
    qualification = _qualification(intent)
    candidate = _candidate(intent)
    durable.save_qualification_ref(qualification)
    durable.save_construction_audit(candidate)

    q = durable.get_qualification_ref(intent.intent_id)
    audit = durable.get_construction_audit(candidate.candidate_portfolio_id)
    assert q["qualification_artifact_sha256"] == qualification.qualification_artifact_sha256
    assert q["dataset_version"] == qualification.dataset_version
    assert audit["request_id"] == candidate.request_id
    assert audit["portfolio_snapshot_ref"] == candidate.portfolio_snapshot_ref
    assert audit["authorizes_execution"] is False


def test_full_audit_chain_and_construction_survive_restart(tmp_path):
    path = tmp_path / "platform.db"
    signal = _signal()
    intent = TradingIntentProposal.from_signal(signal)
    qualification = _qualification(intent)
    candidate = _candidate(intent)
    first = ResearchDurabilityStore(research_store=ResearchStore(path))
    first.persist_audit_bundle(
        decision=_decision(),
        outcome=_outcome(),
        lesson=_lesson(),
        signal=signal,
        intent=intent,
        qualification=qualification,
        candidate=candidate,
    )
    first.close()

    restarted = ResearchDurabilityStore(research_store=ResearchStore(path))
    assert restarted.get_decision("decision-1") == _decision()
    assert restarted.get_signal(signal.signal_id) == signal
    assert restarted.get_intent(intent.intent_id) == intent
    assert restarted.get_qualification_ref(intent.intent_id) is not None
    assert restarted.get_construction_audit("candidate-1") is not None
    links = restarted.trace_links("decision-1")
    relations = {row["relation"] for row in links}
    assert "DECISION_PRODUCED_SIGNAL" in relations
    assert "OUTCOME_FOR_DECISION" in relations
    assert "LESSON_FROM_DECISION" in relations
    assert "SIGNAL_PROPOSED_INTENT" in {
        row["relation"] for row in restarted.trace_links(signal.signal_id)
    }
    assert "INTENT_CONSTRUCTED_CANDIDATE" in {
        row["relation"] for row in restarted.trace_links(intent.intent_id)
    }
    restarted.close()


def test_atomic_bundle_rolls_back_all_prior_writes_on_conflict(durable):
    old_signal = _signal()
    old_intent = TradingIntentProposal.from_signal(old_signal)
    durable.save_intent(old_intent)
    conflicting = replace(old_intent, quality="CONFLICTING")
    new_decision = _decision("decision-bundle")
    new_signal = replace(old_signal, signal_id="signal-bundle")

    with pytest.raises(PersistenceConflictError):
        durable.persist_audit_bundle(
            decision=new_decision,
            signal=new_signal,
            intent=conflicting,
        )

    assert durable.get_decision("decision-bundle") is None
    assert durable.get_signal("signal-bundle") is None


def test_corrupt_payload_fails_closed(durable):
    durable.save_decision(_decision())
    durable.connection.execute(
        "UPDATE research_durable_decisions SET payload_json='{}' WHERE decision_id='decision-1'"
    )
    durable.connection.commit()

    with pytest.raises(PersistenceCorruptError):
        durable.get_decision("decision-1")


def test_unknown_future_schema_version_fails_closed(tmp_path):
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE research_durability_meta (singleton INTEGER PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )
    conn.execute("INSERT INTO research_durability_meta VALUES (1, 999)")
    conn.commit()
    conn.close()

    with pytest.raises(UnsupportedSchemaVersion):
        ResearchDurabilityStore(research_store=ResearchStore(path))


def test_locked_database_fails_closed_with_typed_error(tmp_path):
    path = tmp_path / "locked.db"
    first = ResearchDurabilityStore(research_store=ResearchStore(path))
    second = ResearchDurabilityStore(research_store=ResearchStore(path), busy_timeout_ms=10)
    first.connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(PersistenceBusyError):
            second.save_decision(_decision())
    finally:
        first.connection.rollback()
        first.close()
        second.close()


def test_storage_estimate_is_bounded_and_no_executable_serialization(durable):
    small = durable.estimate_storage(1_000)
    large = durable.estimate_storage(10_000)
    assert 0 < small["estimated_bytes"] < large["estimated_bytes"] < 100_000_000
    assert small["format"] == "typed-json-sqlite"

    source = durable.module_source()
    assert "pickle" not in source
    assert "eval(" not in source
    assert "ExecutionGateway" not in source
    assert "submit_order" not in source


def test_oversized_record_is_rejected_before_sqlite_write(durable):
    oversized = replace(_decision(), assumptions=("x" * 1_100_000,))
    with pytest.raises(ValueError, match="record exceeds"):
        durable.save_decision(oversized)
    assert durable.get_decision("decision-1") is None
