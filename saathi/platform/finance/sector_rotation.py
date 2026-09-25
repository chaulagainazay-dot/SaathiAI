"""Portfolio Sector Rotation — the premium feature the tracker gates, built free.

Compares your portfolio's sector mix against the market's strongest and weakest sectors
(live momentum + breadth), and flags where capital may be misallocated: overweight in
fading sectors, or absent from leading ones. Observation/research only — not advice.
"""
from __future__ import annotations

from typing import Any

AUTHORITY = {"authority": "research_only",
             "disclaimer": "Sector rotation is a research lens over live sector momentum and your holdings — not advice, never an order."}


def _sector_map() -> dict[str, str]:
    """symbol -> sector_name from the live full market."""
    try:
        from saathi.platform.market_data import tracker_web
        rows = tracker_web.today_prices().get("stocks", [])
        return {str(r.get("symbol")).upper(): r.get("sector_name") for r in rows if r.get("symbol")}
    except Exception:
        return {}


def _market_sectors() -> list[dict[str, Any]]:
    try:
        from saathi.platform.market_data import tracker_web
        d = tracker_web.sectors().get("sectors")
        if isinstance(d, dict):
            return d.get("sectors") or d.get("data") or []
        return d or []
    except Exception:
        return []


def rotation() -> dict[str, Any]:
    from saathi.platform.finance import portfolio_desk as pd
    a = pd.analysis()
    positions = a.get("positions", [])
    if not positions:
        return {"available": True, "empty": True, "note": "No holdings yet — add or import a portfolio first.", **AUTHORITY}

    symsec = _sector_map()
    msectors = _market_sectors()
    if not msectors:
        return {"available": False, "error": "sector momentum feed unavailable", **AUTHORITY}

    # market momentum + rank
    ranked = sorted(msectors, key=lambda s: (s.get("sector_percentage_change") or -99), reverse=True)
    n = len(ranked)
    mom = {}
    for i, s in enumerate(ranked):
        name = s.get("sector_name")
        tier = "LEADING" if i < n / 3 else "LAGGING" if i >= 2 * n / 3 else "NEUTRAL"
        mom[name] = {"momentum": s.get("sector_percentage_change"), "rank": i + 1, "tier": tier,
                     "gainers": s.get("gainers"), "losers": s.get("losers"),
                     "company_count": s.get("company_count")}

    # portfolio weights by sector
    total = sum((p.get("value") or 0) for p in positions) or 1.0
    port: dict[str, dict[str, Any]] = {}
    for p in positions:
        sec = symsec.get(p["symbol"].upper()) or "Unknown"
        b = port.setdefault(sec, {"value": 0.0, "symbols": []})
        b["value"] += p.get("value") or 0
        b["symbols"].append(p["symbol"])

    rows = []
    aligned = 0.0
    for sec, b in port.items():
        w = b["value"] / total * 100.0
        m = mom.get(sec, {"momentum": None, "rank": None, "tier": "NEUTRAL"})
        aligned += (w / 100.0) * (m.get("momentum") or 0.0)
        if m["tier"] == "LAGGING" and w >= 15:
            signal, note = "MISALLOCATED", f"Overweight ({w:.0f}%) in a lagging sector — capital may be better rotated out."
        elif m["tier"] == "LAGGING":
            signal, note = "WATCH", "Held in a lagging sector."
        elif m["tier"] == "LEADING":
            signal, note = "WELL-POSITIONED", "Held in a leading sector."
        else:
            signal, note = "NEUTRAL", "Middle-of-pack sector momentum."
        rows.append({"sector": sec, "weight": round(w, 1), "value": round(b["value"]),
                     "symbols": b["symbols"], **m, "signal": signal, "note": note})
    rows.sort(key=lambda r: r["weight"], reverse=True)

    held = set(port.keys())
    # opportunities: leading sectors you don't hold
    opportunities = [{"sector": s.get("sector_name"), "momentum": s.get("sector_percentage_change"),
                      "rank": mom[s.get("sector_name")]["rank"],
                      "top": [c.get("symbol") for c in (s.get("top_companies") or [])[:3]]}
                     for s in ranked[: max(1, n // 3)] if s.get("sector_name") not in held]

    rotate_out = [r["sector"] for r in rows if r["signal"] == "MISALLOCATED"]
    port_avg_mom = round(aligned, 3)
    mkt_avg_mom = round(sum((s.get("sector_percentage_change") or 0) for s in ranked) / n, 3)

    summary = (
        f"Your capital's sector-weighted momentum is {port_avg_mom:+.2f}% vs the market's "
        f"{mkt_avg_mom:+.2f}%. "
        + (f"Rotate-out candidates: {', '.join(rotate_out)}. " if rotate_out else "No heavily-misallocated sectors. ")
        + (f"Leading sectors you're absent from: {', '.join(o['sector'] for o in opportunities[:3])}." if opportunities else "")
    )

    return {
        "available": True, "empty": False,
        "sectors": rows, "opportunities": opportunities,
        "portfolio_momentum": port_avg_mom, "market_momentum": mkt_avg_mom,
        "rotate_out": rotate_out, "summary": summary, **AUTHORITY,
    }
