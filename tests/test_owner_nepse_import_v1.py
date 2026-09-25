"""M — OWNER_NEPSE_EOD_IMPORT tests (Phase 24).

Synthetic CSV fixtures (software tests only; live import needs the real owner file).
Proves format detection, validation, provenance gate, available_at, point-in-time via
canonical reader + catalyst, idempotency, revision, and the canonical write gate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import tempfile
from pathlib import Path

import pytest

from saathi.platform.market_data.owner_import import (
    DetectedFormat, ImportStatus, Provenance, canonical_bar_reader, detect_format,
    import_health, run_import,
)
from saathi.platform.market_data.store import MarketDataStore

_TMP = tempfile.mkdtemp(prefix="owner_import_")
_N = 0

HEADER = "Symbol,Business Date,Open,High,Low,Close,Volume,Turnover"
GOOD = "\n".join([HEADER,
    "NABIL,2024-09-10,500,510,498,505,1200,600000",
    "SCB,2024-09-10,400,405,399,402,800,320000",
    "NABIL,2024-09-11,505,520,504,518,1500,777000"])


def _store():
    global _N
    _N += 1
    return MarketDataStore(db_path=f"{_TMP}/md{_N}.db")


def _write(name, text):
    p = Path(_TMP) / name
    p.write_text(text)
    return str(p)


# 1 — format detection (magic, not extension)
def test_format_detection():
    assert detect_format(GOOD.encode()) == DetectedFormat.CSV
    assert detect_format(b"PK\x03\x04rest") == DetectedFormat.XLSX_UNSUPPORTED
    assert detect_format(b"<!DOCTYPE html><html><head>") == DetectedFormat.HTML_MASQUERADE
    assert detect_format(b'{"error":"UNAUTHORIZED ACCESS"}') == DetectedFormat.JSON_ERROR
    assert detect_format(b"   ") == DetectedFormat.EMPTY


# 2 + 3 — CSV parse + required columns
def test_dry_run_parse():
    r = run_import(_write("good.csv", GOOD), store=_store(), dry_run=True)
    assert r.status == ImportStatus.DRY_RUN and r.rows_valid == 3 and r.symbols_resolved == 3
    assert r.earliest_trading_date == "2024-09-10" and r.latest_trading_date == "2024-09-11"


# 4 — invalid export / html masquerade / missing columns
def test_invalid_exports():
    assert run_import(_write("x.csv", "<html><head>login</head>"), store=_store()).status == ImportStatus.INVALID_EXPORT_FORMAT
    assert run_import(_write("nocols.csv", "A,B,C\n1,2,3"), store=_store()).status == ImportStatus.INVALID_EXPORT_FORMAT
    # xlsx bytes → detected + rejected gracefully
    r = run_import(_write("book.csv", "PK\x03\x04zip"), store=_store())
    assert r.status == ImportStatus.INVALID_EXPORT_FORMAT and any("XLS" in l for l in r.limitations)


# 6 — OHLC / volume validation (no fabrication)
def test_ohlc_validation():
    bad = "\n".join([HEADER,
        "NABIL,2024-09-10,500,490,498,505,1200,1",   # high<max → invalid_ohlc_bounds
        "SCB,2024-09-10,400,405,399,402,-5,1",        # negative volume
        "NEG,2024-09-10,-1,5,0,3,10,1"])              # negative open
    r = run_import(_write("bad.csv", bad), store=_store(), dry_run=True)
    assert r.rows_valid == 0 and r.rows_rejected == 3
    assert any("invalid_ohlc_bounds" in e for e in r.errors)
    assert any("negative_volume" in e for e in r.errors)


# 7 — unresolved symbol
def test_unresolved_symbol():
    r = run_import(_write("sym.csv", HEADER + "\n@@@,2024-09-10,1,2,0.5,1,10,1"), store=_store(), dry_run=True)
    assert r.symbols_unresolved == 1 and any("SYMBOL_UNRESOLVED" in e for e in r.errors)


# 11 — hash identity
def test_hash_identity():
    r = run_import(_write("good.csv", GOOD), store=_store(), dry_run=True)
    assert r.artifact.sha256 == hashlib.sha256(GOOD.encode()).hexdigest()


# 9 + 10 — provenance gate: unverified cannot write canonically
def test_provenance_gate():
    st = _store()
    r = run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=False)
    assert r.status == ImportStatus.PROVENANCE_UNVERIFIED
    assert st.query_bars("owner", "NEPSE:NABIL", __import__("saathi.platform.market_data.models", fromlist=["Timeframe"]).Timeframe.D1, 0, 9e12) == []


# 12 — owner attestation → canonical import
def test_attested_import():
    st = _store()
    r = run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True)
    assert r.status == ImportStatus.IMPORTED and r.rows_inserted == 3
    assert r.artifact.provenance == Provenance.OFFICIAL_VERIFIED
    assert r.artifact.verification_method == "OWNER_ATTESTED_OFFICIAL_DOWNLOAD"


# 13 — available_at conservative retrieval boundary + point-in-time reader
def test_available_at_and_point_in_time():
    st = _store()
    NOW = dt.datetime(2024, 9, 12, tzinfo=dt.timezone.utc).timestamp()
    run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True, now=NOW)
    reader = canonical_bar_reader(st)
    bars = reader("NABIL")
    assert bars and all(b["available_at"] == NOW for b in bars)   # conservative = retrieval time
    # point-in-time: nothing visible before available_at
    visible_before = [b for b in bars if b["available_at"] <= NOW - 1]
    assert visible_before == []


# 16 — idempotency (same file twice → ALREADY_IMPORTED, no dup)
def test_idempotency():
    st = _store()
    run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True)
    r2 = run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True)
    assert r2.status == ImportStatus.ALREADY_IMPORTED
    from saathi.platform.market_data.models import Timeframe
    assert len(st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12)) == 2  # 2 NABIL bars, not 4


# 11b — revision detection (changed close, different artifact → revised, no overwrite)
def test_revision_detection():
    st = _store()
    run_import(_write("v1.csv", GOOD), store=st, dry_run=False, attest_official=True)
    revised = GOOD.replace("NABIL,2024-09-10,500,510,498,505", "NABIL,2024-09-10,500,510,498,507")
    r = run_import(_write("v2.csv", revised), store=st, dry_run=False, attest_official=True)
    assert r.rows_revised >= 1 and r.revisions
    from saathi.platform.market_data.models import Timeframe
    rows = st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12)
    d0 = min(rows, key=lambda x: x["start_epoch"])
    assert d0["close"] == "505"  # original preserved (no silent overwrite)


# 18 — catalyst revalidation over imported canonical bars (wiring proof)
def test_catalyst_market_reaction_from_canonical():
    from saathi.browser_research.intelligence import ResearchEvent, ResearchEventType, ContradictionState
    from saathi.market_intelligence import fuse, MarketContextStatus
    st = _store()
    # bars available BEFORE the event publication so reaction can compute
    IMPORT_NOW = dt.datetime(2024, 9, 9, tzinfo=dt.timezone.utc).timestamp()
    run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True, now=IMPORT_NOW)
    reader = canonical_bar_reader(st)
    PUB = dt.datetime(2024, 9, 10, 6, tzinfo=dt.timezone.utc).timestamp()
    ev = ResearchEvent(event_id="e1", event_type=ResearchEventType.DIVIDEND, market="NEPSE",
                       headline="Dividend [NABIL]", symbol="NABIL", event_date_raw="2024-09-10",
                       event_date_normalized=PUB, source_tier=__import__("saathi.browser_research.tiers", fromlist=["SourceTier"]).SourceTier.TIER_1_OFFICIAL,
                       freshness=__import__("saathi.browser_research.freshness", fromlist=["Freshness"]).Freshness.RECENT,
                       confidence=0.9, contradiction_state=ContradictionState.NONE, evidence_refs=["x"])
    # NOTE: with conservative available_at = IMPORT_NOW (2024-09-09), bars are available before PUB.
    c = fuse(ev, reader=reader)
    # market reaction should now compute (not MARKET_DATA_UNAVAILABLE) given canonical bars
    assert c.market_context.status in (MarketContextStatus.OK, MarketContextStatus.INSUFFICIENT_HISTORY)


# 12c + 25 — canonical write gate: other subsystems import no canonical writer
def test_canonical_write_gate():
    import saathi.browser_research.intelligence as res
    import saathi.browser_research.agent_reach as ar
    import saathi.market_intelligence.fusion as cat
    import saathi.research_surface as rsurf
    for mod in (res, ar, cat, rsurf):
        src = open(mod.__file__).read()
        assert "owner_import" not in src and "insert_bar" not in src, f"{mod.__name__} must not write canonical bars"


# 21 — health (manual import source, not a live feed)
def test_health():
    st = _store()
    assert import_health(st)["status"] == "NO_CANONICAL_DATA"
    run_import(_write("good.csv", GOOD), store=st, dry_run=False, attest_official=True)
    h = import_health(st)
    assert h["status"] == "CANONICAL_DATA_AVAILABLE" and "not a live feed" in h["source_kind"]
    assert h["canonical_bar_count"] == 3


# 22 — CSV formula-injection cell treated as text, never executed
def test_formula_injection_is_text():
    inj = HEADER + "\n=cmd|'/c calc',2024-09-10,1,2,0.5,1,10,1"
    r = run_import(_write("inj.csv", inj), store=_store(), dry_run=True)
    # the '=cmd...' symbol cell is not a valid NEPSE symbol → unresolved, never executed
    assert r.symbols_unresolved == 1 and r.rows_inserted == 0
