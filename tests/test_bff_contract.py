"""Repair 3 regression coverage — BFF payload contract + canonical dream pct.

Guards the two defects introduced by f80a37f ("wire real data"):
1. _top_actions() lost its always-present FINANCE-first action and the
   exactly-3 guarantee.
2. ceo_home() ignored explicitly injected Signals revenue, computing dreamPct
   only from DB state (0 in test envs).
"""
import math

from saathi.bff import ceo_home, Signals
from saathi.financial_mission_control import DREAM_TARGET, dream_progress_pct


# ── payload contract shape ─────────────────────────────────────────────────
REQUIRED_KEYS = (
    "greeting", "priorityScore", "priorityReasons", "executionScore",
    "revenueToday", "dreamTarget", "dreamPct", "actions", "approvals",
    "notifications", "briefing", "quickActions", "calendar", "live",
)


def test_contract_all_required_keys_and_types():
    p = ceo_home()
    for k in REQUIRED_KEYS:
        assert k in p, f"missing {k}"
    assert isinstance(p["actions"], list)
    assert isinstance(p["approvals"], dict)
    assert isinstance(p["notifications"], list)
    assert isinstance(p["briefing"], list)
    assert isinstance(p["dreamPct"], float)
    assert isinstance(p["dreamTarget"], float)
    assert p["live"] is True


def test_contract_actions_exactly_three_finance_first():
    p = ceo_home()
    assert len(p["actions"]) == 3
    assert p["actions"][0]["dept"] == "FINANCE"
    for a in p["actions"]:
        # each action is a real, navigable card
        for key in ("title", "dept", "meta", "tag", "route", "requiresApproval"):
            assert key in a, f"action missing {key}"
        assert a["route"].startswith("/")


def test_contract_stable_with_default_and_explicit_signals():
    # same shape whether Signals are injected or not (empty vs populated state)
    for p in (ceo_home(), ceo_home(Signals()), ceo_home(Signals(revenue_to_date_usd=0.0))):
        assert len(p["actions"]) == 3
        assert p["actions"][0]["dept"] == "FINANCE"
        for k in REQUIRED_KEYS:
            assert k in p


def test_contract_approvals_nested_keys():
    p = ceo_home()
    assert set(p["approvals"].keys()) >= {"count", "items"}
    assert isinstance(p["approvals"]["count"], int)
    assert isinstance(p["approvals"]["items"], list)


# ── canonical dream percentage ─────────────────────────────────────────────
def test_dream_pct_signals_injection_honored():
    p = ceo_home(Signals(revenue_to_date_usd=79388.39))
    assert abs(p["dreamPct"] - 1.0) < 0.01
    assert p["dreamCurrent"] == 79388.39


def test_dream_pct_zero_revenue():
    assert dream_progress_pct(0) == 0.0


def test_dream_pct_zero_target():
    assert dream_progress_pct(1000, target=0) == 0.0


def test_dream_pct_below_equal_above_target():
    assert dream_progress_pct(DREAM_TARGET / 2) == 50.0
    assert dream_progress_pct(DREAM_TARGET) == 100.0
    assert dream_progress_pct(DREAM_TARGET * 2) == 200.0  # exceeding allowed


def test_dream_pct_fractional_and_rounding():
    assert dream_progress_pct(79388.39) == 1.0     # rounds to 4 dp
    v = dream_progress_pct(1000.0)                 # small but visible at 4 dp
    assert 0 < v < 0.1 and v == round(v, 4)
    assert dream_progress_pct(1.0) == 0.0          # below 4-dp resolution floors to 0


def test_dream_pct_negative_and_invalid_inputs():
    assert dream_progress_pct(-500) == 0.0            # no negative progress
    assert dream_progress_pct(None) == 0.0            # missing value
    assert dream_progress_pct("not-a-number") == 0.0  # invalid type
    assert dream_progress_pct(float("nan")) == 0.0    # NaN guard
    assert dream_progress_pct(100, target=-1) == 0.0  # invalid target


def test_dream_pct_is_percentage_not_ratio():
    # canonical semantics: 1.0 means one PERCENT of the dream target
    assert dream_progress_pct(DREAM_TARGET / 100) == 1.0


def test_dream_pct_json_stability():
    import json
    p = ceo_home(Signals(revenue_to_date_usd=79388.39))
    round_trip = json.loads(json.dumps({"dreamPct": p["dreamPct"]}))
    assert round_trip["dreamPct"] == p["dreamPct"]
    assert not math.isnan(p["dreamPct"]) and not math.isinf(p["dreamPct"])
