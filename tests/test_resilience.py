"""RESILIENCE-1 — every critical failure degrades deterministically."""
import pytest

from saathi.platform.tg.resilience import (
    Degradation, FailureMode, Response, degrade, worst,
)


def test_every_failure_mode_has_a_deterministic_decision():
    for mode in FailureMode:
        d = degrade(mode)
        assert isinstance(d, Degradation)
        assert d.response in Response
        assert d.detail


def test_no_failure_ever_auto_retries():
    for mode in FailureMode:
        assert degrade(mode).auto_retry is False, f"{mode} auto-retries"


def test_decisions_are_stable_across_calls():
    for mode in FailureMode:
        assert degrade(mode) == degrade(mode)


@pytest.mark.parametrize("mode", [
    FailureMode.PROVIDER_OUTAGE, FailureMode.DNS_OUTAGE,
    FailureMode.WEBSOCKET_DISCONNECT, FailureMode.STALE_MARKET_DATA,
    FailureMode.SEQUENCE_GAP,
])
def test_market_data_failures_halt_new_orders(mode):
    assert degrade(mode).response == Response.HALT_NEW_ORDERS
    assert degrade(mode).allows_new_orders is False


@pytest.mark.parametrize("mode", [
    FailureMode.OMS_AMBIGUITY, FailureMode.RECONCILIATION_MISMATCH,
    FailureMode.PROCESS_RESTART, FailureMode.DB_RESTART,
])
def test_ambiguous_truth_requires_reconciliation_first(mode):
    assert degrade(mode).response == Response.RECONCILE_FIRST
    assert degrade(mode).allows_new_orders is False


@pytest.mark.parametrize("mode", [
    FailureMode.SCHEMA_DRIFT, FailureMode.PARTIAL_WRITE,
    FailureMode.DISK_PRESSURE, FailureMode.KILL_SWITCH,
])
def test_integrity_failures_fail_closed(mode):
    assert degrade(mode).response == Response.FAIL_CLOSED
    assert degrade(mode).allows_new_orders is False


def test_duplicate_event_is_the_only_benign_mode():
    benign = [m for m in FailureMode if degrade(m).allows_new_orders]
    assert benign == [FailureMode.DUPLICATE_EVENT]


def test_concurrent_failures_take_the_most_restrictive():
    d = worst([FailureMode.DUPLICATE_EVENT, FailureMode.PROVIDER_OUTAGE])
    assert d.response == Response.HALT_NEW_ORDERS
    d2 = worst([FailureMode.PROVIDER_OUTAGE, FailureMode.OMS_AMBIGUITY])
    assert d2.response == Response.RECONCILE_FIRST
    d3 = worst([FailureMode.OMS_AMBIGUITY, FailureMode.KILL_SWITCH])
    assert d3.response == Response.FAIL_CLOSED


def test_unmapped_mode_fails_closed():
    class Fake(str):
        pass
    d = degrade(Fake("SOMETHING_NEW"))
    assert d.response == Response.FAIL_CLOSED
