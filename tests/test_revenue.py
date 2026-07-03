"""Revenue Engine tests (M3 Phase B/#3) — the live Dream Meter, AP-12."""
import pytest

from saathi.revenue import RevenueEngine, RevenueSource, to_usd

NOW = 7_000_000.0


@pytest.fixture
def rev(tmp_path):
    return RevenueEngine(str(tmp_path / "rev.db"), now=lambda: NOW)


def test_records_and_totals_usd(rev):
    rev.record_revenue(source=RevenueSource.YOUTUBE, amount=143.0)
    rev.record_revenue(source=RevenueSource.SUBSCRIPTIONS, amount=57.0)
    assert rev.total_usd() == 200.0


def test_multi_currency_converts_to_usd(rev):
    rev.record_revenue(source=RevenueSource.POS, amount=18400, currency="NPR")  # cafeteria
    rev.record_revenue(source=RevenueSource.YOUTUBE, amount=100, currency="USD")
    # 18400 NPR * 0.0075 = 138.0 + 100 = 238.0
    assert rev.total_usd() == 238.0
    assert to_usd(18400, "NPR") == 138.0


def test_by_source_breakdown(rev):
    rev.record_revenue(source=RevenueSource.YOUTUBE, amount=50)
    rev.record_revenue(source=RevenueSource.YOUTUBE, amount=25)
    rev.record_revenue(source=RevenueSource.TRAVEL, amount=300)
    breakdown = rev.by_source()
    assert breakdown["youtube"] == 75.0
    assert breakdown["travel"] == 300.0


def test_events_published(tmp_path):
    events = []
    rev = RevenueEngine(str(tmp_path / "r.db"),
                        publish=lambda n, p: events.append((n, p)), now=lambda: NOW)
    rev.record_revenue(source=RevenueSource.CRYPTO, amount=1000, note="PEPE gain")
    assert events[0][0] == "revenue.recorded"
    assert events[0][1]["usd"] == 1000.0


def test_dream_meter_goes_live(tmp_path, monkeypatch):
    """record_revenue() lights up the CEO Dashboard Dream Meter."""
    from saathi.ceo_dashboard import CEODashboard
    import saathi.ceo_dashboard as cd
    import saathi.revenue as revmod

    dash = CEODashboard()
    monkeypatch.setattr(cd, "_dashboard", dash)              # fresh dashboard
    engine = RevenueEngine(str(tmp_path / "r.db"), now=lambda: NOW)
    monkeypatch.setattr(revmod, "_engine", engine)

    assert dash.snapshot()["dream"]["connected"] is False
    revmod.record_revenue(source=RevenueSource.YOUTUBE, amount=143.0)
    snap = dash.snapshot()["dream"]
    assert snap["connected"] is True
    assert snap["revenue_total"] == 143.0
    assert snap["progress"] > 0
