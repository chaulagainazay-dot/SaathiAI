"""COMMAND-SURFACE-1 — read-only trading surface; no route bypasses authority."""
from saathi.platform.tg.command_surface import (
    CommandSurface, PanelStatus, markets_panel, portfolio_panel, research_panel,
    safety_panel, trading_panel,
)


def _panel(result, name):
    return next(p for p in result["panels"] if p["panel"] == name)


# ── read-only boundary ───────────────────────────────────────────────────────────
def test_surface_exposes_no_mutating_operation():
    s = CommandSurface()
    for banned in ("submit", "execute", "approve", "cancel", "set_limit",
                   "disable_kill_switch", "place_order", "update"):
        assert not hasattr(s, banned), f"surface exposes {banned}"


def test_surface_authorizes_nothing():
    out = CommandSurface().render()
    assert out["read_only"] is True
    assert out["authorizes_execution"] is False
    assert out["authorizes_approval"] is False


def test_all_five_panels_present():
    out = CommandSurface().render()
    names = [p["panel"] for p in out["panels"]]
    assert names == ["MARKETS", "RESEARCH", "PORTFOLIO", "TRADING", "SAFETY"]


# ── unknown is surfaced, never defaulted to healthy ──────────────────────────────
def test_missing_inputs_render_unknown_not_ok():
    out = CommandSurface().render()
    for name in ("MARKETS", "RESEARCH", "PORTFOLIO", "SAFETY"):
        assert _panel(out, name)["status"] == PanelStatus.UNKNOWN.value
    assert out["overall_status"] in (PanelStatus.UNKNOWN.value, PanelStatus.BLOCKED.value)


def test_stale_and_gapped_providers_degrade_markets():
    p = markets_panel([{"name": "binance", "connected": True, "stale": True, "gap": False}])
    assert p.status == PanelStatus.DEGRADED
    assert p.rows["stale_count"] == 1


def test_disconnected_provider_blocks_markets():
    p = markets_panel([{"name": "binance", "connected": False}])
    assert p.status == PanelStatus.BLOCKED


def test_research_contradictions_degrade():
    p = research_panel([{"id": "t1", "contradictions": 2, "evidence_quality": "CERTIFIED"}])
    assert p.status == PanelStatus.DEGRADED
    assert p.rows["contradiction_count"] == 2


def test_risk_block_blocks_portfolio_panel():
    p = portfolio_panel({"nav": "100000", "cash": "50000"}, None,
                        {"result": "BLOCK", "reason_codes": ["CRYPTO_EXPOSURE_LIMIT"]})
    assert p.status == PanelStatus.BLOCKED
    assert p.rows["risk_reason_codes"] == ["CRYPTO_EXPOSURE_LIMIT"]


def test_open_reconciliation_blocks_trading_panel():
    p = trading_panel(reconciliation={"open_items": [{"instrument_id": "BTC"}]})
    assert p.status == PanelStatus.BLOCKED
    assert p.rows["reconciliation_open_items"]


def test_unknown_orders_block_trading_panel():
    p = trading_panel(oms={"unknown_orders": [{"order_id": "o1"}]})
    assert p.status == PanelStatus.BLOCKED


def test_active_kill_switch_blocks_safety_panel():
    p = safety_panel({"active": True})
    assert p.status == PanelStatus.BLOCKED
    assert p.rows["kill_switch_active"] is True


def test_overall_status_takes_the_worst_panel():
    out = CommandSurface().render(
        provider_health=[{"name": "binance", "connected": True}],
        theses=[{"id": "t", "evidence_quality": "CERTIFIED"}],
        snapshot={"nav": "1", "cash": "1"}, risk={"result": "ALLOW"},
        guardian={"state": "OK"}, oms={"orders": []}, reconciliation={"open_items": []},
        kill_switch={"active": True},  # the only failure
    )
    assert out["overall_status"] == PanelStatus.BLOCKED.value


def test_fully_healthy_surface_is_ok():
    out = CommandSurface().render(
        provider_health=[{"name": "binance", "connected": True}],
        theses=[{"id": "t", "evidence_quality": "CERTIFIED"}],
        snapshot={"nav": "1", "cash": "1"}, risk={"result": "ALLOW"},
        guardian={"state": "OK"}, oms={"orders": []}, reconciliation={"open_items": []},
        kill_switch={"active": False},
    )
    assert out["overall_status"] == PanelStatus.OK.value
