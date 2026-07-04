"""BFF CEO Home contract tests — one aggregated payload, computed & explainable."""
from saathi.bff import ceo_home, compute_priority, Signals


def test_payload_has_full_contract():
    p = ceo_home()
    for k in ("greeting", "priorityScore", "priorityReasons", "executionScore",
              "revenueToday", "dreamTarget", "dreamPct", "actions", "approvals",
              "notifications", "briefing", "quickActions", "calendar", "live"):
        assert k in p, f"missing {k}"
    assert p["live"] is True
    assert 0 <= p["priorityScore"] <= 100
    assert len(p["actions"]) == 3
    assert p["actions"][0]["dept"] == "FINANCE"          # ranked top


def test_priority_is_computed_and_explained():
    score, reasons = compute_priority(Signals(execution_delta_pct=-6, learning_delta_pct=4))
    labels = [r["label"] for r in reasons]
    assert any("Execution down 6%" in l for l in labels)
    assert any("Learning +4%" in l for l in labels)
    # dropping execution lowers the score vs a positive day
    up, _ = compute_priority(Signals(execution_delta_pct=+6))
    assert up > score


def test_high_storage_penalizes_and_flags():
    _, reasons = compute_priority(Signals(storage_pct=0.95))
    assert any("Storage high" in r["label"] for r in reasons)


def test_dream_pct_tracks_revenue():
    p = ceo_home(Signals(revenue_to_date_usd=79388.39))
    assert abs(p["dreamPct"] - 1.0) < 0.01                # ~1% of the dream target
