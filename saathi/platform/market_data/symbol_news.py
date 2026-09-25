"""Per-symbol market news — merges curated research events with real corporate-action
data (announced dividends / bonus / book-close from the NEPSE tracker). Observation-only.

The research surface only covers a handful of curated events (some promoter lock-in /
unlock notices). Most symbols have no research event at all, so we also fold in the
tracker's announced-dividend feed, which is real and covers ~100 symbols. Both are
catalyst-tagged so the UI can flag supply/valuation events.
"""
from __future__ import annotations

import re
from typing import Any

_CAT = re.compile(
    r"dividend|lock[- ]?in|promoter|bonus|right\s*share|book\s*close|agm|auction|delist",
    re.I,
)


def _is_catalyst(text: str) -> bool:
    return bool(_CAT.search(text or ""))


def _research_rows(symbol: str | None, limit: int) -> list[dict[str, Any]]:
    from saathi import research_surface

    events = (research_surface.events(limit=80) or {}).get("events", [])
    rows = []
    for e in events:
        sym = str(e.get("symbol") or "").upper()
        if symbol and sym != symbol:
            continue
        head = e.get("headline") or e.get("title") or e.get("summary") or "(event)"
        rows.append({
            "symbol": sym or None,
            "headline": head,
            "event_type": e.get("event_type"),
            "date": e.get("event_date_normalized") or e.get("event_date_raw"),
            "source": "research",
            "catalyst": _is_catalyst(head + " " + str(e.get("event_type") or "")),
        })
    return rows


def _dividend_rows(symbol: str | None, limit: int) -> list[dict[str, Any]]:
    """Announced dividends → news rows. Per-symbol when given, else recent across market."""
    try:
        from saathi.platform.market_data.tracker.provider import get_provider
        recs, _st = get_provider().dividends(symbol or None)
    except Exception:
        return []
    rows = []
    for r in recs:
        cash = getattr(r, "cash_dividend", None)
        bonus = getattr(r, "bonus_share", None)
        fy = getattr(r, "fiscal_year", "") or ""
        parts = []
        if cash is not None:
            parts.append(f"{cash}% cash")
        if bonus is not None:
            parts.append(f"{bonus}% bonus")
        detail = ", ".join(parts) or "dividend announced"
        bc = getattr(r, "book_close_date", None)
        head = f"Dividend {fy}: {detail}" + (f" · book close {bc}" if bc else "")
        rows.append({
            "symbol": str(getattr(r, "symbol", "") or "").upper() or None,
            "headline": head,
            "event_type": "Dividend / Bonus",
            "date": bc or getattr(r, "published_date", None),
            "source": "tracker",
            "catalyst": True,
        })
    return rows[: limit if symbol else 12]


def symbol_news(symbol: str | None, limit: int = 12) -> dict[str, Any]:
    sym = symbol.strip().upper() if symbol else None
    rows = _research_rows(sym, limit) + _dividend_rows(sym, limit)

    # de-dupe on (symbol, headline)
    seen = set()
    deduped = []
    for r in rows:
        key = (r.get("symbol"), r.get("headline"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # most recent first, then stable re-sort so catalysts float to the top
    deduped.sort(key=lambda r: "" if r.get("date") is None else str(r["date"]), reverse=True)
    deduped.sort(key=lambda r: 0 if r.get("catalyst") else 1)
    out = deduped[: min(int(limit), 40)]
    return {
        "available": True,
        "symbol": sym,
        "count": len(out),
        "events": out,
        "sources": ["research_surface", "nepse_tracker_dividends"],
        "note": None if out else "No corporate-action or research event found for this symbol in the free sources (promoter lock-in/unlock notices are only available for a few curated symbols).",
    }
