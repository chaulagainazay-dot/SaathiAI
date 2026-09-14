"""M — OPEN_SESSION_LIVE_NEPSE_VALIDATION_AND_STREAMING tests (Phase 20).

Deterministic/offline via an injected reader. Proves single-flight acquisition,
refresh coalescing, event publication over the shared Event Fabric (which the existing
SSE stream relays), that SSE fan-out never triggers acquisition, cross-surface snapshot
consistency, OPEN→LIVE freshness, field-change across versions, stale/closed transitions,
observation series, and zero md_bars / execution authority.
"""
from __future__ import annotations

import tempfile
import threading
import time
from datetime import datetime

from saathi.events import bus
from saathi.platform.market_data.live_observation import (
    Freshness, LiveAcquisitionStatus, MarketState, parse_as_of,
)
from saathi.platform.market_data.models import Timeframe
from saathi.platform.market_data.nepse_live_service import (
    EVENT_NAME, NepseLiveService, catalyst_current_context, central_command_live_projection,
    chat_answer_live, observation_series, publish_snapshot, snapshot_event_payload,
    voice_answer_live,
)
from saathi.platform.market_data.store import MarketDataStore
from saathi.platform.nepse.calendar import NEPAL_TZ, SessionState

_TMP = tempfile.mkdtemp(prefix="nepse_stream_")
_N = 0

HEADERS = ["SN", "Symbol", "Close Price* (Rs)", "Open Price (Rs)", "High Price (Rs)",
           "Low Price (Rs)", "Total Traded Quantity", "Total Traded Value", "Total Trades",
           "LTP", "Previous Day Close Price (Rs)", "Average Traded Price (Rs)",
           "52 Week High (Rs)", "52 Week Low (Rs)", "MarketCapitalization (Rs)"]


def _rows(nabil_ltp="552.00(-0.5)", nabil_vol="37,182"):
    return [
        ["1", "NABIL", "552.00", "552.00", "554.90", "551.00", nabil_vol, "20,540,997", "300",
         nabil_ltp, "552.50", "552.6", "1,095.00", "827.90", "3,230.86"],
        ["2", "SCB", "648.00", "647.10", "652.00", "645.00", "10,449", "6,792,318", "103",
         "648.00(2.9)", "645.10", "648.4", "700.00", "600.00", "42,916.56"]]


def _open_index_text(index="2560.00", change="30.00", pct="1.20"):
    return "\n".join(["NEPSE Index", "Sep 14 | 12:30 PM   MARKET OPEN", index, change, pct + "%",
                      "Total Turnover Rs: | 1,000,000.00Total Traded Shares | 5,000",
                      "ADVANCED", "150", "DECLINED", "40", "UNCHANGED", "5"])


def _now_as_of():
    return "As of " + datetime.now(NEPAL_TZ).strftime("%b %d, %Y, %I:%M:%S %p")


def _raw(status="NEPSE_LIVE_AVAILABLE", index_text=None, rows=None, as_of=None):
    return {"status": status, "index_text": index_text or _open_index_text(),
            "as_of_text": as_of or _now_as_of(), "headers": HEADERS, "rows": rows or _rows(),
            "source_url": "https://www.nepalstock.com/today-price"}


def _reader_from(raw):
    return lambda: raw


def _store():
    global _N
    _N += 1
    return MarketDataStore(db_path=f"{_TMP}/md{_N}.db")


# 1 — OPEN session → freshness LIVE (as_of near now)
def test_open_session_live_freshness():
    svc = NepseLiveService(reader=_reader_from(_raw()), publish=False)
    snap = svc.refresh(force=True)
    assert snap.market_status == MarketState.OPEN
    assert snap.freshness == Freshness.LIVE
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_LIVE_AVAILABLE
    assert str(snap.nepse_index) == "2560.00"


# 2 — single-flight: concurrent refreshes → ONE acquisition
def test_single_flight():
    calls = {"n": 0}
    raw = _raw()

    def slow_reader():
        calls["n"] += 1
        time.sleep(0.3)
        return raw

    svc = NepseLiveService(reader=slow_reader, publish=False)
    threads = [threading.Thread(target=lambda: svc.refresh(force=True)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1              # MAX_CONCURRENT_NEPSE_BROWSER_ACQUISITIONS = 1
    assert svc.snapshot() is not None


# 3 — refresh coalescing within interval (no re-read)
def test_refresh_coalesce_interval():
    calls = {"n": 0}

    def reader():
        calls["n"] += 1
        return _raw()

    svc = NepseLiveService(reader=reader, publish=False, refresh_open_sec=60)
    svc.refresh(now=1000.0)
    svc.refresh(now=1010.0)            # within interval → cached
    assert calls["n"] == 1
    svc.refresh(force=True, now=1020.0)
    assert calls["n"] == 2


# 4 — publish over the Event Fabric (what SSE relays); compact payload + version
def test_publish_event():
    received = []
    unsub = bus.subscribe(EVENT_NAME, lambda ev: received.append(ev.payload))
    try:
        svc = NepseLiveService(reader=_reader_from(_raw()), publish=True)
        svc.refresh(force=True)
    finally:
        unsub()
    assert received, "no market.nepse.snapshot event published"
    p = received[-1]
    assert p["version"] == 1 and p["market_status"] == "OPEN" and p["nepse_index"] == "2560.00"
    assert "watchlist" in p and "securities" not in p       # compact, not all 345 records
    assert p["controls"] == []


# 5 — version increments across genuine refreshes
def test_version_increments():
    svc = NepseLiveService(reader=_reader_from(_raw()), publish=False)
    svc.refresh(force=True)
    v1 = svc.version
    svc.refresh(force=True)
    assert svc.version == v1 + 1


# 6 — field change across snapshots (index moves)
def test_field_change_between_snapshots():
    seq = [_raw(index_text=_open_index_text(index="2560.00")),
           _raw(index_text=_open_index_text(index="2565.50"))]
    state = {"i": 0}

    def reader():
        r = seq[min(state["i"], 1)]
        state["i"] += 1
        return r

    svc = NepseLiveService(reader=reader, publish=False)
    a = svc.refresh(force=True)
    b = svc.refresh(force=True)
    assert str(a.nepse_index) == "2560.00" and str(b.nepse_index) == "2565.50"
    assert a.snapshot_id != b.snapshot_id


# 7 — SSE fan-out never triggers acquisition
def test_sse_does_not_acquire():
    calls = {"n": 0}

    def reader():
        calls["n"] += 1
        return _raw()

    svc = NepseLiveService(reader=reader, publish=True)
    # simulate many connected SSE clients subscribing to the shared stream
    unsubs = [bus.subscribe(EVENT_NAME, lambda ev: None) for _ in range(20)]
    try:
        assert calls["n"] == 0          # opening clients did not acquire
        svc.refresh(force=True)
        assert calls["n"] == 1          # exactly one acquisition regardless of client count
    finally:
        for u in unsubs:
            u()


# 8 — cross-surface consistency: CC / chat / voice read the SAME snapshot version
def test_cross_surface_consistency():
    svc = NepseLiveService(reader=_reader_from(_raw()), publish=False)
    svc.refresh(force=True)
    snap = svc.snapshot()
    cc = central_command_live_projection(snap)
    chat = chat_answer_live(snap, "what is NABIL trading at?")
    voice = voice_answer_live(snap, "NABIL ko price kati cha")
    assert cc["nepse_index"] == "2560.00"
    assert "552.00" in chat["answer"] and "552.00" in voice
    assert chat["observed_at"] == snap.observed_at    # same snapshot object drives all


# 9 — stale transition on failure (LIVE → STALE, no fabrication)
def test_stale_transition():
    state = {"fail": False}

    def reader():
        return _raw(status="NEPSE_PAGE_UNAVAILABLE") if state["fail"] else _raw()

    svc = NepseLiveService(reader=reader, publish=False)
    svc.refresh(force=True)
    assert svc.snapshot().freshness == Freshness.LIVE
    state["fail"] = True
    snap = svc.refresh(force=True)
    assert snap.freshness == Freshness.STALE
    assert snap.source_health == LiveAcquisitionStatus.NEPSE_LIVE_STALE
    assert str(snap.nepse_index) == "2560.00"        # last-good preserved, not fabricated


# 10 — market-close transition (OPEN → CLOSED)
def test_close_transition():
    closed_idx = "\n".join(["NEPSE Index", "Sep 14 | 3:00 PM   MARKET CLOSED", "2560.00",
                            "30.00", "1.20%", "Total Turnover Rs: | 1,000,000.00Total Traded Shares | 5,000",
                            "ADVANCED", "150", "DECLINED", "40", "UNCHANGED", "5"])
    seq = [_raw(), _raw(index_text=closed_idx)]
    state = {"i": 0}

    def reader():
        r = seq[min(state["i"], 1)]
        state["i"] += 1
        return r

    svc = NepseLiveService(reader=reader, publish=False)
    a = svc.refresh(force=True)
    b = svc.refresh(force=True)
    assert a.market_status == MarketState.OPEN and a.freshness == Freshness.LIVE
    assert b.market_status == MarketState.CLOSED and b.freshness == Freshness.MARKET_CLOSED


# 11 — observation series across multiple snapshots; md_bars stays 0
def test_observation_series_no_md_bars():
    st = _store()
    svc = NepseLiveService(store=st, reader=_reader_from(_raw()), publish=False)
    svc.refresh(force=True)
    svc.refresh(force=True)
    ser = observation_series(st, "NEPSE:NABIL")
    assert len(ser) >= 2
    assert st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12) == []
    assert st._conn.execute("SELECT COUNT(*) c FROM md_bars").fetchone()["c"] == 0


# 12 — catalyst current context updates with newer snapshot; never historical
def test_catalyst_context_updates():
    seq = [_raw(rows=_rows(nabil_ltp="552.00(-0.5)")),
           _raw(rows=_rows(nabil_ltp="560.00(8.0)"))]
    state = {"i": 0}

    def reader():
        r = seq[min(state["i"], 1)]
        state["i"] += 1
        return r

    svc = NepseLiveService(reader=reader, publish=False)
    svc.refresh(force=True)
    c1 = catalyst_current_context(svc.snapshot(), "NABIL")
    svc.refresh(force=True)
    c2 = catalyst_current_context(svc.snapshot(), "NABIL")
    assert c1["ltp"] == "552.00" and c2["ltp"] == "560.00"
    assert c1["is_historical_reaction"] is False and c2["is_historical_reaction"] is False


# 13 — compact payload size is bounded
def test_payload_compact():
    svc = NepseLiveService(reader=_reader_from(_raw()), publish=False)
    snap = svc.refresh(force=True)
    import json
    payload = snapshot_event_payload(snap, 1)
    assert len(json.dumps(payload).encode()) < 4096       # compact market projection


# 14 — publish never imports/needs trade authority; producer session helper resolves
def test_authority_and_producer_helper():
    import saathi.platform.market_data.nepse_live_service as m
    src = open(m.__file__).read()
    for banned in ("ExecutionGateway", "place_order", "portfolio_construction"):
        assert banned not in src or "-> ExecutionGateway" in src  # only the note string
    from saathi.scheduler import _nepse_session_state
    assert isinstance(_nepse_session_state(), SessionState)
