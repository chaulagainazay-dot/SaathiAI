"""M — AUTOMATED_OFFICIAL_NEPSE_ARTIFACT_ACQUISITION tests (Phase 22).

Deterministic/offline: injected fake acquirer + a synthetic official-schema CSV. Proves
the acquisition→canonical-import wiring, provenance (OFFICIAL_BROWSER_DOWNLOAD), domain
governance, failure containment, and that only the importer writes canonical bars.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from saathi.platform.market_data.nepse_acquire import (
    AcquisitionResult, AcquisitionStatus, _origin_ok, acquire_and_import, acquisition_health,
)
from saathi.platform.market_data.owner_import import ImportStatus
from saathi.platform.market_data.store import MarketDataStore

_TMP = tempfile.mkdtemp(prefix="nepse_acq_")
_N = 0
# real official NEPSE Today's-Price header shape
OFFICIAL_CSV = "\n".join([
    "Id,Business Date,Security Id,Symbol,Security Name,Open Price,High Price,Low Price,Close Price,Total Traded Quantity,Total Traded Value,Previous Day Close Price",
    "1,2026-09-11,131,NABIL,Nabil Bank Limited,552,554.9,551,552,37182,20540997,552.5",
    "2,2026-09-11,133,SCB,Standard Chartered,647.1,652,645,648,10449,6792318,645.1",
    "3,2026-09-11,134,HBL,Himalayan Bank,185.2,188,185,188,49771,9296948,185.2"])


def _store():
    global _N
    _N += 1
    return MarketDataStore(db_path=f"{_TMP}/md{_N}.db")


def _fake_acquirer(status=AcquisitionStatus.DOWNLOAD_AVAILABLE, csv=OFFICIAL_CSV):
    def acq(*, dest_dir=None):
        if status != AcquisitionStatus.DOWNLOAD_AVAILABLE:
            return AcquisitionResult(status, limitations=["simulated"])
        p = Path(_TMP) / f"today_{_N}.csv"
        p.write_text(csv)
        import hashlib
        return AcquisitionResult(
            AcquisitionStatus.DOWNLOAD_AVAILABLE, acquisition_id="acq_test",
            source_url="https://www.nepalstock.com/today-price",
            download_url="blob:https://www.nepalstock.com/abc", retrieved_at=1.0,
            download_filename="Today's Price - 2026-09-11.csv", local_path=str(p),
            detected_format="CSV", file_size=len(csv.encode()),
            sha256=hashlib.sha256(csv.encode()).hexdigest(),
            provenance_status="OFFICIAL_BROWSER_DOWNLOAD")
    return acq


# 1 — official-domain / origin governance
def test_origin_governance():
    assert _origin_ok("blob:https://www.nepalstock.com/uuid") is True
    assert _origin_ok("https://nepalstock.com/api/x") is True
    assert _origin_ok("https://evil.example/x") is False
    assert _origin_ok("blob:https://evil.example/x") is False


# 2 — acquire + canonical import via OFFICIAL_BROWSER_DOWNLOAD provenance
def test_acquire_and_import():
    st = _store()
    out = acquire_and_import(store=st, acquirer=_fake_acquirer())
    assert out["status"] == "IMPORTED" and out["canonical_write"] is True
    imp = out["import"]
    assert imp["rows_inserted"] == 3
    assert imp["artifact"]["provenance"] == "OFFICIAL_VERIFIED"
    assert imp["artifact"]["verification_method"] == "OFFICIAL_BROWSER_DOWNLOAD"


# 3 — schema mapping of real official columns (Open Price/High Price/... , Business Date)
def test_official_schema_mapping():
    st = _store()
    out = acquire_and_import(store=st, acquirer=_fake_acquirer())
    imp = out["import"]
    assert imp["symbols_resolved"] == 3 and imp["earliest_trading_date"] == "2026-09-11"
    from saathi.platform.market_data.models import Timeframe
    bars = st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12)
    assert bars and bars[0]["close"] == "552" and bars[0]["open"] == "552"


# 4 — idempotency (same artifact twice → ALREADY_IMPORTED)
def test_idempotency():
    st = _store()
    acq = _fake_acquirer()
    acquire_and_import(store=st, acquirer=acq)
    out2 = acquire_and_import(store=st, acquirer=acq)
    assert out2["status"] == "ALREADY_IMPORTED"


# 5 — failure containment: no artifact → no canonical write, no fallback
def test_failure_containment():
    st = _store()
    for s in (AcquisitionStatus.NOT_YET_PUBLISHED, AcquisitionStatus.SITE_UNAVAILABLE,
              AcquisitionStatus.ANTI_BOT_BLOCKED, AcquisitionStatus.PLAYWRIGHT_UNAVAILABLE):
        out = acquire_and_import(store=_store(), acquirer=_fake_acquirer(status=s))
        assert out["canonical_write"] is False and out["import"] is None
    from saathi.platform.market_data.models import Timeframe
    assert st.query_bars("owner", "NEPSE:NABIL", Timeframe.D1, 0, 9e12) == []


# 6 — unexpected download origin → not imported
def test_unexpected_origin_blocked():
    # a fake acquirer that reports success but the real acquire() would reject bad origin;
    # here we assert _origin_ok gates it (unit) + that a degraded acquisition never writes
    out = acquire_and_import(store=_store(),
                             acquirer=_fake_acquirer(status=AcquisitionStatus.UNEXPECTED_DOWNLOAD_ORIGIN))
    assert out["canonical_write"] is False


# 7 — health (automated official browser download, not a live feed)
def test_health():
    st = _store()
    acquire_and_import(store=st, acquirer=_fake_acquirer())
    h = acquisition_health(st)
    assert h["status"] == "CANONICAL_DATA_AVAILABLE" and "not a live feed" in h["source_kind"]
    assert h["canonical_bar_count"] == 3


# 8 — canonical write gate: acquisition module never scrapes DOM / writes bars directly
def test_no_dom_or_direct_write():
    import saathi.platform.market_data.nepse_acquire as m
    src = open(m.__file__).read()
    assert "insert_bar" not in src                      # never writes bars directly
    assert "query_selector" not in src and "inner_text" not in src  # no DOM price scraping
    assert "expect_download" in src                     # uses the official download event
    # only writes via the importer
    assert "run_import" in src


# 9 — no trade authority imports
def test_no_authority_imports():
    import saathi.platform.market_data.nepse_acquire as m
    imports = [l for l in open(m.__file__).read().splitlines()
               if l.strip().startswith(("import ", "from "))]
    blob = "\n".join(imports)
    for banned in ("execution.gateway", "trading_guardian", "broker", "portfolio_construction"):
        assert banned not in blob


# 10 — point-in-time available_at from acquisition (conservative = import time)
def test_point_in_time_available_at():
    st = _store()
    out = acquire_and_import(store=st, acquirer=_fake_acquirer())
    from saathi.platform.market_data.owner_import import canonical_bar_reader
    bars = canonical_bar_reader(st)("NABIL")
    assert bars and all(b["available_at"] > 0 for b in bars)
    av = bars[0]["available_at"]
    visible_before = [b for b in bars if b["available_at"] <= av - 1]
    assert visible_before == []
