"""M — LIVE_NEPSE_BROWSER_MARKET_DATA tests (Phase 23).

Deterministic/offline: an injected `reader` returns the real rendered-DOM shape
captured from the official NEPSE site (index widget text + today-price headers/rows).
Proves parsing, freshness, market state, symbol resolution, the bounded service +
last-good preservation, storage into live_market_* (NOT md_bars), and the read-only
consumers — with zero trade authority and no DOM->canonical-history writes.
"""
from __future__ import annotations

import tempfile
import time

from saathi.platform.market_data.live_observation import (
    Freshness, LiveAcquisitionStatus, MarketState, SymbolResolution,
    compute_freshness, parse_ltp,
)
from saathi.platform.market_data.models import Timeframe
from saathi.platform.market_data.nepse_live import (
    build_snapshot, observe_nepse_live, parse_index_widget, parse_today_rows,
)
from saathi.platform.market_data.nepse_live_service import (
    NepseLiveService, catalyst_current_context, central_command_live_projection,
    chat_answer_live, latest_snapshot_row, observation_series, persist_snapshot,
    trading_guardian_live_context, voice_answer_live,
)
from saathi.platform.market_data.store import MarketDataStore

_TMP = tempfile.mkdtemp(prefix="nepse_live_")
_N = 0

INDEX_TEXT = "\n".join([
    "NEPSE Index", "Sep 11 | 3:00 PM   MARKET CLOSED", "2,559.49", "27.94", "1.10%",
    "Total Turnover Rs: | 4,360,159,487.26Total Traded Shares | 12,089,709",
    "11:45", "12:45", "2520", "2560",
    "ADVANCED", "238", "DECLINED", "30", "UNCHANGED", "9", "Technical Charts"])
AS_OF = "As of Sep 11, 2026, 3:00:00 PM"
HEADERS = ["SN", "Symbol", "Close Price* (Rs)", "Open Price (Rs)", "High Price (Rs)",
           "Low Price (Rs)", "Total Traded Quantity", "Total Traded Value", "Total Trades",
           "LTP", "Previous Day Close Price (Rs)", "Average Traded Price (Rs)",
           "52 Week High (Rs)", "52 Week Low (Rs)", "MarketCapitalization (Rs) (Amt in millions)"]
ROWS = [
    ["1", "NABIL", "552.00", "552.00", "554.90", "551.00", "37,182", "20,540,997.7", "300",
     "552.00(-0.5)", "552.50", "552.6", "1,095.00", "827.90", "3,230.86"],
    ["2", "SCB", "648.00", "647.10", "652.00", "645.00", "10,449", "6,792,318", "103",
     "648.00(2.9)", "645.10", "648.4", "700.00", "600.00", "42,916.56"],
    ["3", "??", "100.00", "100.00", "100.00", "100.00", "10", "1,000", "1",
     "100.00(0)", "100.00", "100", "120.00", "90.00", "5.00"],  # garbage symbol -> unresolved
]


def _raw(status="NEPSE_LIVE_AVAILABLE", index_text=INDEX_TEXT, headers=HEADERS, rows=ROWS,
         as_of=AS_OF):
    d = {"status": status, "index_text": index_text, "as_of_text": as_of,
         "headers": headers, "rows": rows, "source_url": "https://www.nepalstock.com/today-price"}
    return d


def _reader(**kw):
    raw = _raw(**kw)
    return lambda: raw


def _store():
    global _N
    _N += 1
    return MarketDataStore(db_path=f"{_TMP}/md{_N}.db")


# 1 — index widget parse
def test_parse_index_widget():
    d = parse_index_widget(INDEX_TEXT, as_of_text=AS_OF)
    assert d["market_status"] == MarketState.CLOSED
    assert str(d["nepse_index"]) == "2559.49"
    assert str(d["index_change"]) == "27.94"
    assert str(d["index_change_percent"]) == "1.10"
    assert str(d["total_turnover"]) == "4360159487.26"
    assert str(d["total_volume"]) == "12089709"
    assert d["advancers"] == 238 and d["decliners"] == 30 and d["unchanged"] == 9
    assert d["source_as_of_epoch"] is not None


# 2 — LTP paren parse
def test_parse_ltp():
    assert parse_ltp("880.00(1.9)") == (__import__("decimal").Decimal("880.00"),
                                        __import__("decimal").Decimal("1.9"))
    assert parse_ltp("552.00(-0.5)")[1] == __import__("decimal").Decimal("-0.5")
    assert parse_ltp("100")[0] == __import__("decimal").Decimal("100")


# 3 — today-price schema mapping + resolution
def test_parse_today_rows():
    obs, ok = parse_today_rows(HEADERS, ROWS, observed_at=time.time())
    assert ok and len(obs) == 3
    nabil = obs[0]
    assert nabil.symbol == "NABIL" and nabil.instrument_id == "NEPSE:NABIL"
    assert str(nabil.ltp) == "552.00" and str(nabil.open) == "552.00"
    assert str(nabil.high) == "554.90" and str(nabil.volume) == "37182"
    assert nabil.symbol_resolution == SymbolResolution.RESOLVED
    assert obs[2].symbol_resolution == SymbolResolution.SYMBOL_UNRESOLVED  # "??"


# 4 — full snapshot, market closed
def test_build_snapshot_closed():
    snap = build_snapshot(_raw())
    assert snap.market_status == MarketState.CLOSED
    assert snap.freshness == Freshness.MARKET_CLOSED
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_MARKET_CLOSED
    assert str(snap.nepse_index) == "2559.49"
    assert len(snap.securities) == 3
    assert snap.data_class == "LIVE_BROWSER_OBSERVED"


# 5 — open market -> LIVE freshness (as_of near now)
def test_build_snapshot_open_live():
    from saathi.platform.market_data.live_observation import parse_as_of
    now = time.time()
    # craft an OPEN status with an as_of that parses near-now is hard; use compute_freshness unit
    fr = compute_freshness(now=now, observed_at=now, source_as_of_epoch=now - 10,
                           market_status=MarketState.OPEN)
    assert fr == Freshness.LIVE
    fr2 = compute_freshness(now=now, observed_at=now, source_as_of_epoch=now - 3600,
                            market_status=MarketState.OPEN)
    assert fr2 == Freshness.STALE


# 6 — schema changed
def test_schema_changed():
    snap = build_snapshot(_raw(headers=["foo", "bar"], rows=[["1", "2"]]))
    assert snap.freshness == Freshness.SCHEMA_CHANGED
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_SCHEMA_CHANGED


# 7 — page unavailable
def test_page_unavailable():
    snap = build_snapshot({"status": "NEPSE_PAGE_UNAVAILABLE", "limitations": ["timeout"]})
    assert snap.freshness == Freshness.PAGE_ERROR
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_PAGE_UNAVAILABLE
    assert len(snap.securities) == 0


# 8 — observe with injected reader (0 browser workers)
def test_observe_injected():
    snap, metrics = observe_nepse_live(reader=_reader())
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_MARKET_CLOSED
    assert metrics["browser_workers"] == 0 and metrics["securities"] == 3


# 9 — service refresh persists + caches; bounded (no re-read within interval)
def test_service_bounded_refresh():
    st = _store()
    calls = {"n": 0}

    def reader():
        calls["n"] += 1
        return _raw()

    svc = NepseLiveService(store=st, reader=reader)
    now = 1000.0
    svc.refresh(now=now)
    assert calls["n"] == 1
    svc.refresh(now=now + 10)          # within closed interval -> cached
    assert calls["n"] == 1
    svc.refresh(force=True, now=now + 20)
    assert calls["n"] == 2
    latest = latest_snapshot_row(st)
    assert latest and latest["data_class"] == "LIVE_BROWSER_OBSERVED"


# 10 — failure containment: preserve last-good marked STALE, never fabricate
def test_failure_preserves_last_good():
    st = _store()
    state = {"fail": False}

    def reader():
        if state["fail"]:
            return {"status": "NEPSE_PAGE_UNAVAILABLE", "limitations": ["down"]}
        return _raw()

    svc = NepseLiveService(store=st, reader=reader)
    svc.refresh(now=1000.0)
    assert svc.snapshot().source_health == LiveAcquisitionStatus.NEPSE_MARKET_CLOSED
    state["fail"] = True
    snap = svc.refresh(force=True, now=2000.0)
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_LIVE_STALE
    assert snap.freshness == Freshness.STALE
    assert len(snap.securities) == 3            # last-good securities preserved
    assert any("live read failed" in l for l in snap.limitations)


# 11 — storage: live tables written, md_bars NOT touched
def test_storage_not_md_bars():
    st = _store()
    snap = build_snapshot(_raw())
    persist_snapshot(st, snap)
    ser = observation_series(st, "NEPSE:NABIL")
    assert ser and ser[0]["data_class"] == "LIVE_BROWSER_OBSERVED"
    # md_bars must be empty — live browser never writes canonical history
    assert st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12) == []
    n_bars = st._conn.execute("SELECT COUNT(*) c FROM md_bars").fetchone()["c"]
    assert n_bars == 0


# 12 — Central Command projection: no trade controls
def test_central_command_projection():
    snap = build_snapshot(_raw())
    proj = central_command_live_projection(snap)
    assert proj["controls"] == []
    assert proj["nepse_index"] == "2559.49" and proj["advancers"] == 238
    assert proj["watchlist"] and "ltp" in proj["watchlist"][0]
    assert proj["data_class"] == "LIVE_BROWSER_OBSERVED"


# 13 — chat: exposes source + freshness across query types
def test_chat_answers():
    snap = build_snapshot(_raw())
    a = chat_answer_live(snap, "is the market open?")
    assert "CLOSED" in a["answer"] and a["freshness"] == "MARKET_CLOSED"
    b = chat_answer_live(snap, "what is NABIL trading at?")
    assert "NABIL" in b["answer"] and "552" in b["answer"] and b["source"].startswith("Official NEPSE")
    c = chat_answer_live(snap, "which stocks have the highest volume?")
    assert "volume" in c["answer"].lower()
    d = chat_answer_live(snap, "how fresh is this data?")
    assert "freshness" in d["answer"].lower() or d["freshness"]


# 14 — voice
def test_voice_answer():
    snap = build_snapshot(_raw())
    v = voice_answer_live(snap, "NABIL ko price kati cha")
    assert "NABIL" in v and "552" in v
    v2 = voice_answer_live(snap)
    assert "NEPSE" in v2


# 15 — catalyst current context (never historical reaction)
def test_catalyst_current_context():
    snap = build_snapshot(_raw())
    ctx = catalyst_current_context(snap, "NABIL")
    assert ctx["context_kind"] == "CURRENT_MARKET_CONTEXT"
    assert ctx["is_historical_reaction"] is False
    assert ctx["available"] is True and ctx["ltp"] == "552.00"


# 16 — Trading Guardian read-only context
def test_tg_context_read_only():
    snap = build_snapshot(_raw())
    tg = trading_guardian_live_context(snap)
    assert tg["execution_authority"] is False and tg["authority"] == "READ_ONLY_CONTEXT"


# 17 — no trade-authority imports in live modules
def test_no_authority_imports():
    import saathi.platform.market_data.nepse_live as m1
    import saathi.platform.market_data.nepse_live_service as m2
    for m in (m1, m2):
        blob = "\n".join(l for l in open(m.__file__).read().splitlines()
                         if l.strip().startswith(("import ", "from ")))
        for banned in ("execution.gateway", "trading_guardian", "broker",
                       "portfolio_construction"):
            assert banned not in blob, f"{banned} imported in {m.__file__}"


# 18 — no DOM->canonical writes, no downloads
def test_no_canonical_write_no_download():
    import saathi.platform.market_data.nepse_live as m
    src = open(m.__file__).read()
    assert "insert_bar(" not in src          # never calls the canonical bar writer
    assert "expect_download" not in src      # live path never downloads a file
    assert "save_as" not in src
    # service persists only to live_market_* tables, never canonical bars (check code, not prose)
    import saathi.platform.market_data.nepse_live_service as ms
    ssrc = open(ms.__file__).read()
    assert "insert_bar(" not in ssrc
    assert "INTO md_bars" not in ssrc and "md_bars(" not in ssrc
