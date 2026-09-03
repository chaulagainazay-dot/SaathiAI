"""CI-LANES-1 — core certification must never require live network."""
from saathi.platform.tg.ci_lanes import (
    LANES, LANES_BY_NAME, OFFLINE_MARKERS, certification_policy, core_lanes, network_lanes,
)


def test_every_core_lane_is_offline():
    for lane in core_lanes():
        assert lane.network_allowed is False, f"{lane.name} allows network"
        assert lane.marker_expr == OFFLINE_MARKERS, f"{lane.name} weakens the offline markers"


def test_only_the_canary_lane_may_use_the_network():
    assert [lane.name for lane in network_lanes()] == ["PUBLIC_LIVE_DATA_CANARY"]


def test_canary_never_gates_certification():
    canary = LANES_BY_NAME["PUBLIC_LIVE_DATA_CANARY"]
    assert canary.required_for_certification is False


def test_browser_lane_excluded_from_deterministic_core():
    browser = LANES_BY_NAME["BROWSER_UI"]
    assert browser.required_for_certification is False


def test_offline_marker_excludes_every_nondeterministic_category():
    for category in ("browser", "live", "external", "network"):
        assert f"not {category}" in OFFLINE_MARKERS


def test_expected_lanes_present():
    expected = {
        "OFFLINE_CORE", "TRADING_AUTHORITY", "RESEARCH", "SIGNAL", "BACKTEST",
        "NEPSE", "CRYPTO", "PORTFOLIO", "PAPER", "REPLAY", "RESILIENCE_SECURITY",
        "BROWSER_UI", "PUBLIC_LIVE_DATA_CANARY",
    }
    assert expected.issubset(set(LANES_BY_NAME))


def test_pytest_args_are_reproducible():
    lane = LANES_BY_NAME["CRYPTO"]
    args = lane.pytest_args()
    assert args[0] == "tests"
    assert "-m" in args and OFFLINE_MARKERS in args
    assert "-k" in args
    assert lane.pytest_args() == args


def test_policy_summary():
    p = certification_policy()
    assert p["core_offline_only"] is True
    assert p["network_lanes"] == ["PUBLIC_LIVE_DATA_CANARY"]
    assert p["core_lane_count"] == len(core_lanes())


def test_lane_names_unique():
    names = [lane.name for lane in LANES]
    assert len(names) == len(set(names))
