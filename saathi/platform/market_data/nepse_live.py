"""M — LIVE_NEPSE_BROWSER_MARKET_DATA: governed live NEPSE browser observer.

SaathiOS opens the OFFICIAL public NEPSE website with governed Playwright and reads
the CURRENTLY RENDERED market DOM (index widget + today-price table). No file
downloads, no XHR/token replay (the site's JSON endpoints are 401 — anti-bot; we do
not defeat them), no broker/TMS pages, no CAPTCHA bypass. One browser, one context,
one page; torn down after each read. READ-ONLY.

Output is a `NepseLiveMarketSnapshot` tagged LIVE_BROWSER_OBSERVED. It is CURRENT
awareness only — it is never written to `md_bars` (the canonical historical plane)
and never becomes historical market-reaction evidence. Browser read (`_read_raw_dom`)
is separated from pure parsing so parsing is fully offline-testable via an injected
`reader`.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field

from saathi.browser.policy import check_domain
from saathi.platform.market_data.live_observation import (
    ACQUISITION_METHOD, DATA_CLASS, EXCHANGE, SOURCE_AUTHORITY,
    Freshness, LiveAcquisitionStatus, LiveMarketObservation, MarketState,
    NepseLiveMarketSnapshot, SymbolResolution,
    compute_freshness, market_state_from_text, num, parse_as_of, parse_ltp,
)

SOURCE_HOME = "https://www.nepalstock.com/"
SOURCE_TODAY_PRICE = "https://www.nepalstock.com/today-price"
ALLOWED_HOSTS = ("nepalstock.com",)
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_INDEX_WIDGET_SELECTOR = "[class*='index']"
_PAGE_SIZE = 500                     # today-price rows/page (full universe in one page)
_RENDER_WAIT_MS = 7000

# today-price header substring -> observation field
_HEADER_MAP = {
    "symbol": "symbol", "open price": "open", "high price": "high", "low price": "low",
    "close price": "close", "total traded quantity": "volume",
    "total traded value": "turnover", "total trades": "transactions", "ltp": "ltp",
    "previous day close": "previous_close", "average traded price": "average_price",
    "52 week high": "week52_high", "52 week low": "week52_low",
    "marketcapitalization": "market_cap", "market capitalization": "market_cap",
}
_REQUIRED_FIELDS = ("symbol", "ltp", "open", "high", "low")


# ── symbol resolution (reuses the instrument master; never guesses) ─────────────
def _resolve_symbol(symbol: str) -> tuple[str, SymbolResolution]:
    from saathi.platform.nepse.instruments import instrument_id_for
    try:
        return instrument_id_for(symbol), SymbolResolution.RESOLVED
    except Exception:
        return "", SymbolResolution.SYMBOL_UNRESOLVED


# ── pure parsing (offline-testable) ─────────────────────────────────────────────
def parse_index_widget(widget_text: str, *, as_of_text: str = "") -> dict:
    """Extract market-wide fields from the homepage NEPSE-index widget inner text."""
    lines = [l.strip() for l in (widget_text or "").splitlines() if l.strip()]
    joined = "\n".join(lines)
    out: dict = {}
    # market status
    status_line = next((l for l in lines if re.search(r"MARKET\s+(OPEN|CLOSE|PRE)", l, re.I)), "")
    out["market_status"] = market_state_from_text(status_line)
    # index value / change / percent: numbers following the status line
    nums_after: list = []
    seen_status = False
    for l in lines:
        if l == status_line:
            seen_status = True
            continue
        if not seen_status:
            continue
        if re.fullmatch(r"[-+]?[\d,]+(?:\.\d+)?%?", l):
            nums_after.append(l)
        if len(nums_after) >= 3:
            break
    if nums_after:
        out["nepse_index"] = num(nums_after[0])
    if len(nums_after) >= 2:
        out["index_change"] = num(nums_after[1])
    if len(nums_after) >= 3:
        out["index_change_percent"] = num(nums_after[2].rstrip("%"))
    # turnover / traded shares
    m = re.search(r"Total Turnover Rs:\s*\|?\s*([\d,]+(?:\.\d+)?)", joined, re.I)
    if m:
        out["total_turnover"] = num(m.group(1))
    m = re.search(r"Total Traded Shares\s*\|?\s*([\d,]+)", joined, re.I)
    if m:
        out["total_volume"] = num(m.group(1))
    # breadth: label then next numeric line
    for label, key in (("ADVANCED", "advancers"), ("DECLINED", "decliners"),
                       ("UNCHANGED", "unchanged")):
        for i, l in enumerate(lines):
            if l.upper() == label and i + 1 < len(lines):
                v = num(lines[i + 1])
                if v is not None:
                    out[key] = int(v)
                break
    raw, epoch = parse_as_of(as_of_text or joined)
    out["source_as_of"] = raw
    out["source_as_of_epoch"] = epoch
    return out


def _header_index(headers: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    for i, h in enumerate(headers):
        hl = (h or "").strip().lower()
        for sub, field_name in _HEADER_MAP.items():
            if sub in hl and field_name not in idx:
                idx[field_name] = i
    return idx


def parse_today_rows(headers: list[str], rows: list[list[str]], *, observed_at: float,
                     source_as_of: str = "", source_url: str = SOURCE_TODAY_PRICE
                     ) -> tuple[list[LiveMarketObservation], bool]:
    """Parse the today-price table. Returns (observations, schema_ok)."""
    hidx = _header_index(headers)
    schema_ok = all(f in hidx for f in _REQUIRED_FIELDS)
    if not schema_ok:
        return [], False
    obs: list[LiveMarketObservation] = []

    def cell(row, fname):
        i = hidx.get(fname)
        return row[i] if (i is not None and i < len(row)) else None

    for row in rows:
        sym = (cell(row, "symbol") or "").strip()
        if not sym:
            continue
        inst, resolution = _resolve_symbol(sym)
        ltp, pt = parse_ltp(cell(row, "ltp"))
        prev = num(cell(row, "previous_close"))
        pct = None
        if pt is not None and prev not in (None, 0):
            try:
                pct = (pt / prev) * 100
            except Exception:
                pct = None
        obs.append(LiveMarketObservation(
            observation_id=f"lmo_{uuid.uuid4().hex[:12]}", symbol=sym, instrument_id=inst,
            observed_at=observed_at, source_url=source_url, ltp=ltp,
            open=num(cell(row, "open")), high=num(cell(row, "high")), low=num(cell(row, "low")),
            close=num(cell(row, "close")), previous_close=prev,
            volume=num(cell(row, "volume")), turnover=num(cell(row, "turnover")),
            transactions=num(cell(row, "transactions")), point_change=pt, percent_change=pct,
            average_price=num(cell(row, "average_price")),
            week52_high=num(cell(row, "week52_high")), week52_low=num(cell(row, "week52_low")),
            market_cap=num(cell(row, "market_cap")), source_as_of=source_as_of,
            symbol_resolution=resolution,
            limitations=() if resolution == SymbolResolution.RESOLVED else ("symbol not in NEPSE master",)))
    return obs, True


def build_snapshot(raw: dict, *, now: float | None = None) -> NepseLiveMarketSnapshot:
    """Assemble a snapshot from a raw DOM dict (from `_read_raw_dom` or a test reader).

    raw keys: status(LiveAcquisitionStatus name|None), index_text, as_of_text,
    headers(list), rows(list[list]), source_url, limitations(list)."""
    now = now if now is not None else time.time()
    limitations = list(raw.get("limitations") or [])
    status_name = raw.get("status")
    # hard failure path — no usable DOM
    if status_name and status_name != LiveAcquisitionStatus.NEPSE_LIVE_AVAILABLE.value:
        health = LiveAcquisitionStatus(status_name)
        fr = {
            LiveAcquisitionStatus.PLAYWRIGHT_UNAVAILABLE: Freshness.UNAVAILABLE,
            LiveAcquisitionStatus.NEPSE_PAGE_UNAVAILABLE: Freshness.PAGE_ERROR,
            LiveAcquisitionStatus.NEPSE_ACCESS_BLOCKED: Freshness.PAGE_ERROR,
            LiveAcquisitionStatus.NEPSE_SCHEMA_CHANGED: Freshness.SCHEMA_CHANGED,
            LiveAcquisitionStatus.NEPSE_BROWSER_FAILED: Freshness.UNAVAILABLE,
        }.get(health, Freshness.UNAVAILABLE)
        return NepseLiveMarketSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}", observed_at=now,
            source_url=raw.get("source_url", SOURCE_HOME), market_status=MarketState.UNKNOWN,
            freshness=fr, source_health=health, limitations=tuple(limitations))

    idx = parse_index_widget(raw.get("index_text", ""), as_of_text=raw.get("as_of_text", ""))
    securities, schema_ok = parse_today_rows(
        raw.get("headers", []), raw.get("rows", []), observed_at=now,
        source_as_of=idx.get("source_as_of", ""), source_url=raw.get("source_url", SOURCE_TODAY_PRICE))
    if not schema_ok and not securities:
        limitations.append("today-price schema not recognized")
        return NepseLiveMarketSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}", observed_at=now,
            source_url=raw.get("source_url", SOURCE_TODAY_PRICE),
            market_status=idx.get("market_status", MarketState.UNKNOWN),
            freshness=Freshness.SCHEMA_CHANGED,
            source_health=LiveAcquisitionStatus.NEPSE_SCHEMA_CHANGED, limitations=tuple(limitations))

    mstate = idx.get("market_status", MarketState.UNKNOWN)
    fresh = compute_freshness(now=now, observed_at=now,
                              source_as_of_epoch=idx.get("source_as_of_epoch"), market_status=mstate)
    health = (LiveAcquisitionStatus.NEPSE_MARKET_CLOSED if mstate == MarketState.CLOSED
              else LiveAcquisitionStatus.NEPSE_LIVE_STALE if fresh == Freshness.STALE
              else LiveAcquisitionStatus.NEPSE_LIVE_AVAILABLE)
    unresolved = sum(1 for o in securities if o.symbol_resolution == SymbolResolution.SYMBOL_UNRESOLVED)
    if unresolved:
        limitations.append(f"{unresolved} symbol(s) unresolved")
    return NepseLiveMarketSnapshot(
        snapshot_id=f"snap_{uuid.uuid4().hex[:12]}", observed_at=now,
        source_url=raw.get("source_url", SOURCE_TODAY_PRICE), market_status=mstate,
        freshness=fresh, source_health=health,
        nepse_index=idx.get("nepse_index"), index_change=idx.get("index_change"),
        index_change_percent=idx.get("index_change_percent"),
        total_turnover=idx.get("total_turnover"), total_volume=idx.get("total_volume"),
        advancers=idx.get("advancers"), decliners=idx.get("decliners"),
        unchanged=idx.get("unchanged"), securities=tuple(securities),
        source_as_of=idx.get("source_as_of", ""), source_as_of_epoch=idx.get("source_as_of_epoch"),
        limitations=tuple(limitations))


# ── governed browser read (the ONLY networked part) ─────────────────────────────
def _read_raw_dom(*, timeout_sec: float = 45.0, page_size: int = _PAGE_SIZE) -> dict:
    """One-shot governed Playwright read of the rendered NEPSE market DOM.
    Returns a raw dict for `build_snapshot`. Never downloads, never replays XHR."""
    for seed in (SOURCE_HOME, SOURCE_TODAY_PRICE):
        if not check_domain(seed, allowed_hosts=list(ALLOWED_HOSTS)).allowed:
            return {"status": LiveAcquisitionStatus.NEPSE_ACCESS_BLOCKED.value,
                    "limitations": ["seed failed domain policy"], "source_url": seed}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"status": LiveAcquisitionStatus.PLAYWRIGHT_UNAVAILABLE.value,
                "limitations": ["playwright not installed"], "source_url": SOURCE_HOME}
    browser = pw = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--disable-http2", "--no-sandbox"])
        ctx = browser.new_context(user_agent=_UA)
        page = ctx.new_page()
        # per-response domain revalidation (defense in depth; no XHR bodies consumed)
        offdomain: list[str] = []
        page.on("response", lambda r: (offdomain.append(r.url[:120])
                 if not check_domain(r.url, allowed_hosts=list(ALLOWED_HOSTS)).allowed else None))
        # homepage index widget + "As of"
        page.goto(SOURCE_HOME, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
        page.wait_for_timeout(_RENDER_WAIT_MS)
        widget = page.locator(_INDEX_WIDGET_SELECTOR)
        index_text = widget.first.inner_text() if widget.count() else ""
        body_txt = page.locator("body").inner_text()
        as_of = next((l.strip() for l in body_txt.splitlines() if l.strip().lower().startswith("as of")), "")
        # today-price table at full page size
        page.goto(SOURCE_TODAY_PRICE, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
        page.wait_for_timeout(_RENDER_WAIT_MS)
        # widen the today-price page size to load the full universe in one page.
        try:
            sel = page.locator("select").first
            if sel.count():
                chosen = None
                for how in (dict(label=str(page_size)), dict(value=str(page_size))):
                    try:
                        sel.select_option(**how)
                        chosen = how
                        break
                    except Exception:
                        continue
                if chosen is None:
                    # fall back to the largest available option
                    opts = [o.strip() for o in sel.locator("option").all_inner_texts()]
                    biggest = max((o for o in opts if o.replace(",", "").isdigit()),
                                  key=lambda o: int(o.replace(",", "")), default=None)
                    if biggest:
                        sel.select_option(label=biggest)
                # the page applies the chosen size only when its Filter control is clicked
                # (read-only re-render of the same public table; no download, no data entry)
                fb = page.locator("button:has-text('Filter')")
                if fb.count():
                    fb.first.click(timeout=6000)
                page.wait_for_timeout(4000)
        except Exception:
            pass
        table = page.locator("table").first
        if table.count() == 0:
            return {"status": LiveAcquisitionStatus.NEPSE_SCHEMA_CHANGED.value,
                    "limitations": ["today-price table not found"], "source_url": SOURCE_TODAY_PRICE}
        headers = [h.strip() for h in table.locator("thead th").all_inner_texts()]
        rows = []
        rlocs = table.locator("tbody tr")
        for i in range(rlocs.count()):
            rows.append([c.strip() for c in rlocs.nth(i).locator("td").all_inner_texts()])
        lims = []
        if offdomain:
            lims.append(f"{len(offdomain)} off-domain response(s) ignored")
        return {"status": LiveAcquisitionStatus.NEPSE_LIVE_AVAILABLE.value,
                "index_text": index_text, "as_of_text": as_of, "headers": headers,
                "rows": rows, "source_url": SOURCE_TODAY_PRICE, "limitations": lims}
    except Exception as e:
        msg = str(e).lower()
        st = (LiveAcquisitionStatus.NEPSE_ACCESS_BLOCKED
              if any(k in msg for k in ("captcha", "403", "forbidden", "blocked"))
              else LiveAcquisitionStatus.NEPSE_PAGE_UNAVAILABLE)
        return {"status": st.value, "limitations": [f"{type(e).__name__}: {str(e)[:140]}"],
                "source_url": SOURCE_HOME}
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            if pw is not None:
                pw.stop()
        except Exception:
            pass


def observe_nepse_live(*, reader=None, page_size: int = _PAGE_SIZE, timeout_sec: float = 45.0,
                       now: float | None = None) -> tuple[NepseLiveMarketSnapshot, dict]:
    """Observe live NEPSE market state. `reader` (test injection) returns the raw DOM
    dict; default is the governed browser read. Returns (snapshot, metrics)."""
    t0 = time.time()
    rss_mb = None
    ru0 = _children_maxrss_mb()
    read = reader or (lambda: _read_raw_dom(timeout_sec=timeout_sec, page_size=page_size))
    raw = read()
    if reader is None:
        ru1 = _children_maxrss_mb()
        if ru0 is not None and ru1 is not None:
            rss_mb = round(max(0.0, ru1 - ru0), 1) or ru1
    snap = build_snapshot(raw, now=now)
    metrics = {"latency_sec": round(time.time() - t0, 3), "browser_rss_mb": rss_mb,
               "browser_workers": 0 if reader is not None else 1,
               "securities": len(snap.securities), "source_health": snap.source_health.value}
    return snap, metrics


def _children_maxrss_mb() -> float | None:
    """Peak RSS of child processes (the Playwright chromium) via getrusage.
    macOS reports ru_maxrss in bytes; Linux in KiB."""
    try:
        import resource
        import sys
        rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        div = (1024 * 1024) if sys.platform == "darwin" else 1024
        return round(rss / div, 1)
    except Exception:
        return None
