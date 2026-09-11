"""RECONCILIATION-V2 — multi-market fail-closed reconciliation invariants."""
from decimal import Decimal

import pytest

from saathi.platform.tg.reconciliation_v2 import (
    ReconciliationAuthorityV2, ReconSource, ReconStatus, reconcile_snapshot,
)


def test_matching_snapshot_is_healthy():
    r = reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.5"}, source=ReconSource.PAPER_CRYPTO)
    assert r.status == ReconStatus.HEALTHY
    assert r.blocking is False


def test_quantity_mismatch_blocks():
    r = reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.4"}, source=ReconSource.PAPER_CRYPTO)
    assert r.status == ReconStatus.MISMATCH
    assert r.blocking is True


def test_tolerance_respected():
    r = reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.4999"},
                           source=ReconSource.PAPER_CRYPTO, tolerance="0.001")
    assert r.status == ReconStatus.HEALTHY


def test_absent_observation_is_data_insufficient_not_healthy():
    r = reconcile_snapshot({"BTC": "1"}, None, source=ReconSource.PAPER_CRYPTO)
    assert r.status == ReconStatus.DATA_INSUFFICIENT
    assert r.blocking is True


def test_expected_instrument_missing_from_observed_is_not_assumed_zero():
    r = reconcile_snapshot({"BTC": "1", "ETH": "2"}, {"BTC": "1"},
                           source=ReconSource.PAPER_CRYPTO)
    assert r.status == ReconStatus.DATA_INSUFFICIENT
    assert any(f.instrument_id == "ETH" for f in r.findings)


def test_unknown_observed_instrument_is_mismatch():
    r = reconcile_snapshot({}, {"DOGE": "100"}, source=ReconSource.PAPER_CRYPTO)
    assert r.status == ReconStatus.MISMATCH


def test_nepse_source_supported():
    r = reconcile_snapshot({"NEPSE:NABIL": "10"}, {"NEPSE:NABIL": "20"},
                           source=ReconSource.PAPER_NEPSE)
    assert r.status == ReconStatus.MISMATCH
    assert r.findings[0].source == ReconSource.PAPER_NEPSE


# ── authority: no silent healing ─────────────────────────────────────────────────
def test_later_healthy_snapshot_does_not_silently_heal():
    auth = ReconciliationAuthorityV2()
    auth.record(reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.4"},
                                   source=ReconSource.PAPER_CRYPTO))
    assert auth.is_blocked(ReconSource.PAPER_CRYPTO) is True

    # a later, perfectly healthy snapshot arrives
    auth.record(reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.5"},
                                   source=ReconSource.PAPER_CRYPTO))
    assert auth.is_blocked(ReconSource.PAPER_CRYPTO) is True, "healed silently"
    assert len(auth.open_items()) == 1


def test_explicit_resolution_clears_and_requires_actor_and_note():
    auth = ReconciliationAuthorityV2()
    auth.record(reconcile_snapshot({"BTC": "1.5"}, {"BTC": "1.4"},
                                   source=ReconSource.PAPER_CRYPTO))
    with pytest.raises(ValueError):
        auth.resolve(ReconSource.PAPER_CRYPTO, "BTC", actor="", note="")
    assert auth.resolve(ReconSource.PAPER_CRYPTO, "BTC",
                        actor="operator:human", note="venue restated fill") is True
    assert auth.is_blocked(ReconSource.PAPER_CRYPTO) is False
    assert auth.open_items() == []


def test_sources_are_isolated():
    auth = ReconciliationAuthorityV2()
    auth.record(reconcile_snapshot({"BTC": "1"}, {"BTC": "2"},
                                   source=ReconSource.PAPER_CRYPTO))
    assert auth.is_blocked(ReconSource.PAPER_CRYPTO) is True
    assert auth.is_blocked(ReconSource.PAPER_NEPSE) is False
    assert auth.is_blocked() is True  # any source


def test_real_readonly_source_available_for_future_use():
    r = reconcile_snapshot({"BTC": "1"}, {"BTC": "1"}, source=ReconSource.REAL_READONLY)
    assert r.status == ReconStatus.HEALTHY
