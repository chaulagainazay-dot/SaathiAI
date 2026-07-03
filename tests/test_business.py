"""Business OS tests (M3) — universal activity ingestion, cafeteria, KPI engine, AP-12."""
import pytest

from saathi.business import BusinessOS, KPIEngine
from saathi.revenue import RevenueSource


def _os():
    episodes, revenues = [], []
    bos = BusinessOS(
        record_episode=lambda **kw: episodes.append(kw) or len(episodes),
        record_revenue=lambda **kw: revenues.append(kw) or len(revenues))
    return bos, episodes, revenues


# ── universal entry point ──────────────────────────────────────────────────
def test_record_activity_creates_episode_and_revenue():
    bos, episodes, revenues = _os()
    bos.record_activity(department="Travel", product="travel", activity="booking",
                        metrics={"destination": "Australia", "pax": 2},
                        revenue_usd=1900, revenue_source=RevenueSource.TRAVEL)
    assert episodes[0]["department"] == "Travel"
    assert episodes[0]["metadata"]["destination"] == "Australia"
    assert revenues[0]["amount"] == 1900
    assert revenues[0]["source"] is RevenueSource.TRAVEL


def test_activity_without_revenue_only_records_episode():
    bos, episodes, revenues = _os()
    bos.record_activity(department="Travel", product="travel", activity="lead",
                        metrics={"source": "instagram"})
    assert len(episodes) == 1 and len(revenues) == 0


# ── cafeteria: the Dal Bhat example ────────────────────────────────────────
def test_cafeteria_day_generates_recommendation():
    bos, episodes, revenues = _os()
    out = bos.record_cafeteria_day(item="Dal Bhat", produced=180, sold=171,
                                   revenue_usd=138.0, currency="NPR")
    assert out["waste"] == 9
    assert out["waste_pct"] == 0.05
    assert out["recommended_reduction"] == 6                # 9 * 2/3, safety buffer
    assert "Reduce Dal Bhat tomorrow by 6 portions" == out["recommendation"]
    # recorded as an episode carrying the recommendation, + POS revenue
    assert episodes[0]["metadata"]["recommendation"].startswith("Reduce Dal Bhat")
    assert revenues[0]["source"] is RevenueSource.POS


def test_cafeteria_no_waste_keeps_steady():
    bos, episodes, _ = _os()
    out = bos.record_cafeteria_day(item="Momo", produced=100, sold=100)
    assert out["recommended_reduction"] == 0
    assert "steady" in out["recommendation"]
    assert episodes[0]["outcome"] == "success"


# ── KPI engine ─────────────────────────────────────────────────────────────
@pytest.fixture
def kpi(tmp_path):
    return KPIEngine(str(tmp_path / "kpi.db"), now=lambda: 8_000_000.0)


def test_kpi_on_track_higher_is_better(kpi):
    kpi.define_kpi(name="daily_revenue", department="Cafeteria", target=100,
                   higher_is_better=True, is_north_star=True)
    kpi.record_value("daily_revenue", 138)
    c = kpi.compare("daily_revenue")
    assert c.on_track is True
    assert c.vs_target_pct == 1.38
    assert kpi.north_stars()[0].name == "daily_revenue"


def test_kpi_lower_is_better_waste(kpi):
    kpi.define_kpi(name="waste_pct", department="Cafeteria", target=0.05,
                   higher_is_better=False)
    kpi.record_value("waste_pct", 0.09)         # above target → not on track
    c = kpi.compare("waste_pct")
    assert c.on_track is False


def test_kpi_no_data_is_not_on_track(kpi):
    kpi.define_kpi(name="mrr", department="Telegram", target=500)
    c = kpi.compare("mrr")
    assert c.latest is None and c.on_track is False
