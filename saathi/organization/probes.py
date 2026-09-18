"""Deterministic, READ-ONLY work units that organization mission steps perform.

Every probe reads an existing SaathiOS source (paper ledger tables, the market
data store, the Evidence Service, Trading Guardian posture, the PortfolioRisk
budget) and returns a structured result. Probes never call an LLM, never write
to any store other than through their return value, never call the
ExecutionGateway, and never evaluate proposals that could lead to an order.

Result contract (``ProbeResult`` dict):
  status   : "complete" | "awaiting_evidence" | "error"
  summary  : one line
  findings : list[str]           — facts derived from data
  gaps     : list[str]           — what is missing and why
  evidence : list[{source, ref, detail}]
  data     : dict                — small structured payload
  llm_used : False (always, in this milestone)
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent.parent
STALE_BAR_SEC = 86400.0  # PortfolioRisk budget max_mark_age_seconds


def _result(status: str, summary: str, *, findings=(), gaps=(), evidence=(), data=None) -> dict:
    return {"status": status, "summary": summary, "findings": list(findings),
            "gaps": list(gaps), "evidence": list(evidence), "data": data or {},
            "llm_used": False}


def _platform_db() -> Path:
    env = os.environ.get("SAATHI_PLATFORM_DB")
    return Path(env) if env else ROOT / "data" / "platform" / "platform.db"


def _ro(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _age(ts: float) -> str:
    s = max(0.0, time.time() - ts)
    if s < 3600:
        return f"{int(s // 60)} min"
    if s < 86400:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} days"


# ── portfolio (paper ledger, read-only) ─────────────────────────────────────
def _paper_state() -> dict | None:
    p = _platform_db()
    if not p.exists():
        return None
    with _ro(p) as c:
        accts = [dict(r) for r in c.execute(
            "SELECT id,name,base_currency,starting_cash,current_cash,environment,status "
            "FROM paper_accounts")]
        pos = [dict(r) for r in c.execute(
            "SELECT account_id,symbol,quantity,avg_cost FROM paper_positions WHERE quantity<>0")]
    return {"accounts": accts, "positions": pos}


def paper_portfolio(ctx: dict) -> dict:
    st = _paper_state()
    if st is None:
        return _result("awaiting_evidence", "Paper ledger store not present",
                       gaps=["platform.db paper tables unavailable"])
    if not st["accounts"]:
        return _result("awaiting_evidence", "No paper accounts exist",
                       gaps=["Create a paper account to review a portfolio"])
    envs = {a["environment"] for a in st["accounts"]}
    findings = [f"{len(st['accounts'])} paper account(s), environment {', '.join(sorted(envs))}",
                f"{len(st['positions'])} open position(s): "
                + ", ".join(f"{p['symbol']} ×{float(p['quantity']):g}" for p in st["positions"])]
    gaps = ["Positions valued at average cost — no mark prices for these symbols in the market-data store"]
    return _result("complete", f"Read {len(st['accounts'])} paper accounts, {len(st['positions'])} positions",
                   findings=findings, gaps=gaps,
                   evidence=[{"source": "paper_ledger", "ref": "platform.db:paper_accounts,paper_positions",
                              "detail": "read-only query"}],
                   data=st)


def _budget() -> dict:
    from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
    return PortfolioRiskEngine().get_risk_budget()   # pure: returns the static budget


def _weights(st: dict) -> list[dict]:
    rows = []
    for a in st["accounts"]:
        nav = float(a["current_cash"] or 0) + sum(
            float(p["quantity"]) * float(p["avg_cost"]) for p in st["positions"] if p["account_id"] == a["id"])
        for p in st["positions"]:
            if p["account_id"] != a["id"] or nav <= 0:
                continue
            w = float(p["quantity"]) * float(p["avg_cost"]) / nav
            rows.append({"account": a["name"], "symbol": p["symbol"], "weight": round(w, 4),
                         "cost_value": round(float(p["quantity"]) * float(p["avg_cost"]), 2),
                         "nav_at_cost": round(nav, 2)})
    return rows


def exposure(ctx: dict) -> dict:
    st = _paper_state()
    if not st or not st["accounts"]:
        return _result("awaiting_evidence", "No paper portfolio to measure", gaps=["paper ledger empty"])
    ws = _weights(st)
    gross = {}
    for r in ws:
        gross[r["account"]] = gross.get(r["account"], 0) + r["weight"]
    b = _budget()
    findings = [f"{acct}: gross exposure {g:.1%} of NAV (budget max {float(b['max_gross_exposure']):.0%})"
                for acct, g in gross.items()]
    return _result("complete", "Exposure measured at cost against PortfolioRisk budget",
                   findings=findings,
                   gaps=["Exposure uses cost basis, not marks; authoritative evaluation stays in PortfolioRiskEngine"],
                   evidence=[{"source": "portfolio_risk_budget", "ref": b.get("version"), "detail": "static budget"}],
                   data={"gross": gross, "weights": ws})


def concentration(ctx: dict) -> dict:
    st = _paper_state()
    if not st or not st["accounts"]:
        return _result("awaiting_evidence", "No paper portfolio to measure", gaps=["paper ledger empty"])
    b = _budget()
    cap = float(b["max_position_weight"])
    ws = _weights(st)
    over = [r for r in ws if r["weight"] > cap]
    findings = [f"{r['symbol']} in {r['account']}: {r['weight']:.1%} of NAV" for r in ws]
    findings.append(f"{len(over)} position(s) above the {cap:.0%} single-position budget")
    return _result("complete", f"Concentration: {len(over)} above budget", findings=findings,
                   evidence=[{"source": "portfolio_risk_budget", "ref": b.get("version"),
                              "detail": "max_position_weight"}],
                   data={"over_budget": over, "cap": cap})


# ── market data ─────────────────────────────────────────────────────────────
def _bars(prefix: str) -> list[dict]:
    p = _platform_db()
    if not p.exists():
        return []
    with _ro(p) as c:
        return [dict(r) for r in c.execute(
            "SELECT instrument,timeframe,open,high,low,close,volume,end_epoch,quality "
            "FROM md_bars WHERE instrument LIKE ?", (prefix + "%",))]


def crypto_market_data(ctx: dict) -> dict:
    bars = [b for b in _bars("") if not b["instrument"].startswith("NEPSE:")]
    if not bars:
        return _result("awaiting_evidence", "No crypto bars recorded",
                       gaps=["Market-data store holds no crypto bars; technical analysis needs recorded OHLCV"])
    return _result("complete", f"{len(bars)} crypto bars available",
                   evidence=[{"source": "market_data", "ref": "md_bars", "detail": f"{len(bars)} bars"}])


def nepse_market_snapshot(ctx: dict) -> dict:
    bars = [b for b in _bars("NEPSE:") if b["timeframe"] == "1d"]
    if not bars:
        return _result("awaiting_evidence", "No NEPSE daily bars recorded",
                       gaps=["Import NEPSE bars into the market-data store"])
    latest = max(b["end_epoch"] for b in bars)
    adv = sum(1 for b in bars if b["close"] > b["open"])
    dec = sum(1 for b in bars if b["close"] < b["open"])
    valid = sum(1 for b in bars if b["quality"] == "VALID")
    stale = time.time() - latest > STALE_BAR_SEC
    top = sorted(bars, key=lambda b: (b["volume"] or 0), reverse=True)[:5]
    findings = [f"{len(bars)} instruments, latest session close {time.strftime('%Y-%m-%d', time.gmtime(latest))}",
                f"Intraday breadth (close vs open): {adv} up / {dec} down / {len(bars) - adv - dec} flat",
                "Highest volume: " + ", ".join(b["instrument"].split(":")[1] for b in top)]
    gaps = []
    if stale:
        gaps.append(f"Latest bars are {_age(latest)} old — older than the 24 h mark-age budget")
    if valid < len(bars):
        gaps.append(f"{len(bars) - valid} bars not VALID quality")
    return _result("complete", f"NEPSE snapshot: {adv} advancing / {dec} declining",
                   findings=findings, gaps=gaps,
                   evidence=[{"source": "market_data", "ref": "platform.db:md_bars",
                              "detail": f"{len(bars)} daily bars, age {_age(latest)}"}],
                   data={"instruments": len(bars), "advancing": adv, "declining": dec,
                         "latest_epoch": latest, "stale": stale})


def nepse_sector(ctx: dict) -> dict:
    p = _platform_db()
    n = 0
    if p.exists():
        with _ro(p) as c:
            n = c.execute("SELECT COUNT(*) FROM md_instruments").fetchone()[0]
    if not n:
        return _result("awaiting_evidence", "No sector classification recorded",
                       gaps=["md_instruments is empty — banking/sector filtering cannot be done "
                             "without a recorded sector taxonomy per symbol"])
    return _result("complete", f"{n} instruments with metadata",
                   evidence=[{"source": "market_data", "ref": "md_instruments", "detail": f"{n} rows"}])


def nepse_swing(ctx: dict) -> dict:
    bars = _bars("NEPSE:")
    per: dict[str, int] = {}
    for b in bars:
        per[b["instrument"]] = per.get(b["instrument"], 0) + 1
    deepest = max(per.values()) if per else 0
    if deepest < 20:
        return _result("awaiting_evidence", "Insufficient price history for swing analysis",
                       gaps=[f"At most {deepest} daily bar(s) per instrument; swing setups need ≥ 20"],
                       data={"max_bars_per_instrument": deepest})
    return _result("complete", "Sufficient history for swing screening",
                   data={"max_bars_per_instrument": deepest})


# ── governed research (Evidence Service) ────────────────────────────────────
def governed_research(ctx: dict) -> dict:
    import json
    from saathi.evidence.store import default_store
    rows = default_store().query(department="browser_research", limit=200)
    if not rows:
        return _result("awaiting_evidence", "No governed research evidence recorded",
                       gaps=["Run a governed NEPSE browser research mission first"])
    newest = max(float(r.get("timestamp") or 0) for r in rows)
    facts, hosts, tiers = [], set(), {}
    for r in rows:
        try:
            m = json.loads(r.get("metrics") or "{}")
        except Exception:
            m = {}
        if m.get("statement"):
            facts.append(m["statement"])
            hosts.add(m.get("source_host", "?"))
            t = m.get("source_tier", "UNKNOWN")
            tiers[t] = tiers.get(t, 0) + 1
    gaps = []
    if time.time() - newest > 86400:
        gaps.append(f"Newest research evidence is {_age(newest)} old")
    return _result("complete", f"{len(facts)} governed facts from {len(hosts)} source(s)",
                   findings=[f"{f}" for f in facts[:6]],
                   gaps=gaps,
                   evidence=[{"source": "evidence_service", "ref": r["id"],
                              "detail": r.get("episode") or ""} for r in rows[:8]],
                   data={"facts": len(facts), "hosts": sorted(hosts), "tiers": tiers,
                         "newest_epoch": newest})


def source_freshness(ctx: dict) -> dict:
    snap = nepse_market_snapshot(ctx)
    res = governed_research(ctx)
    findings, gaps = [], []
    if snap["status"] == "complete":
        findings.append(f"Market data age: {_age(snap['data']['latest_epoch'])}")
        gaps += [g for g in snap["gaps"] if "old" in g]
    else:
        gaps.append("No market data to date")
    if res["status"] == "complete":
        findings.append(f"Research evidence age: {_age(res['data']['newest_epoch'])}; "
                        f"tiers {res['data']['tiers']}")
        gaps += res["gaps"]
    else:
        gaps.append("No research evidence to date")
    return _result("complete", "Source freshness checked", findings=findings, gaps=gaps)


# ── risk / authority (read-only posture) ────────────────────────────────────
def guardian_posture(ctx: dict) -> dict:
    from saathi.platform.trading_guardian import safety_posture
    from saathi.platform.tg.service import default_tg_service
    sp = safety_posture()
    tg = default_tg_service().posture()
    ks = tg.get("kill_switch") or {}
    findings = [f"Highest permitted target: {sp.get('HIGHEST_PERMITTED_TARGET')}",
                f"Live execution: {sp.get('LIVE_EXECUTION')}",
                f"Authority mode: {tg.get('authority_mode')} (paper_only={tg.get('paper_only')})",
                f"LLM may approve: {tg.get('llm_boundary', {}).get('may_approve')}"]
    if isinstance(ks, dict) and ks:
        findings.append(f"Kill switch: {ks}")
    return _result("complete", "Trading Guardian posture read (paper-only)", findings=findings,
                   evidence=[{"source": "trading_guardian", "ref": tg.get("engine_version"),
                              "detail": "posture()"}],
                   data={"paper_only": tg.get("paper_only"), "live": sp.get("LIVE_EXECUTION"),
                         "authority_mode": tg.get("authority_mode")})


def risk_budget_check(ctx: dict) -> dict:
    b = _budget()
    conc = concentration(ctx)
    findings = [f"Budget {b['version']}: max position {float(b['max_position_weight']):.0%}, "
                f"max drawdown {float(b['max_drawdown']):.0%}, min cash {float(b['min_cash_buffer']):.0%}",
                f"Leverage {'on' if b['leverage_enabled'] else 'off'}, shorts {'on' if b['shorts_enabled'] else 'off'}"]
    findings += conc["findings"][-1:]
    return _result("complete", "Positions compared with PortfolioRisk budget", findings=findings,
                   gaps=["Authoritative limit evaluation remains in PortfolioRiskEngine "
                         "(not invoked here: it records NAV history)"],
                   evidence=[{"source": "portfolio_risk_budget", "ref": b["version"], "detail": "budget"}])


def stress_engine(ctx: dict) -> dict:
    return _result("awaiting_evidence", "Engine stress test not run",
                   gaps=["PortfolioRiskEngine.run_stress needs bound fund-ledger state; organization "
                         "missions do not bind ledgers (read-only boundary)"])


def compliance_posture(ctx: dict) -> dict:
    g = guardian_posture(ctx)
    ok = g["data"].get("paper_only") is True and g["data"].get("live") == "DISABLED"
    return _result("complete",
                   "Paper-only posture verified" if ok else "Posture NOT paper-only — escalate",
                   findings=g["findings"][:3], evidence=g["evidence"], data={"paper_only_verified": ok})


# ── synthesis (deterministic digests of child outputs) ──────────────────────
def _children(ctx: dict) -> list[dict]:
    return [c for c in ctx.get("children", []) if c]


def desk_digest(ctx: dict) -> dict:
    ch = _children(ctx)
    done = [c for c in ch if c["output"].get("status") == "complete"]
    gaps = [g for c in ch for g in c["output"].get("gaps", [])]
    findings = [f"{c['role_name']}: {c['output'].get('summary')}" for c in ch]
    status = "complete" if done else "awaiting_evidence"
    return _result(status, f"Desk digest: {len(done)}/{len(ch)} specialist inputs complete",
                   findings=findings, gaps=gaps)


def challenge_gaps(ctx: dict) -> dict:
    prior = ctx.get("prior", [])
    gaps = sorted({g for p in prior for g in p["output"].get("gaps", [])})
    return _result("complete", f"Challenged {len(prior)} inputs — {len(gaps)} open gaps",
                   findings=[f"Unverified: {g}" for g in gaps[:10]], data={"open_gaps": gaps})


def fund_manager_synthesis(ctx: dict) -> dict:
    ch = _children(ctx)
    findings = [f"{c['role_name']}: {c['output'].get('summary')}" for c in ch]
    gaps = sorted({g for c in ch for g in c["output"].get("gaps", [])})
    return _result("complete",
                   "Portfolio view assembled — no rebalance proposal issued (insufficient marked data)"
                   if gaps else "Portfolio view assembled",
                   findings=findings, gaps=gaps,
                   data={"proposal": None,
                         "proposal_reason": "Deterministic inputs incomplete; a proposal requires marks, "
                                            "history and engine risk evaluation"})


def committee_synthesis(ctx: dict) -> dict:
    prior = ctx.get("prior", [])
    support = [f"{p['role_name']}: {f}" for p in prior if p["output"].get("status") == "complete"
               for f in p["output"].get("findings", [])[:2]]
    missing = sorted({g for p in prior for g in p["output"].get("gaps", [])})
    confidence = "LOW" if len(missing) > 3 else ("MEDIUM" if missing else "HIGH")
    return _result("complete", f"Committee proposal: HOLD / GATHER EVIDENCE (confidence {confidence})",
                   findings=support[:8], gaps=missing,
                   data={"proposal": "HOLD_AND_GATHER_EVIDENCE",
                         "supporting_evidence": support[:8],
                         "opposing_evidence": [],
                         "agreement": "Members concur data is insufficient for an allocation change",
                         "disagreement": [],
                         "uncertainty": confidence,
                         "missing_information": missing,
                         "committee_engine": "InvestmentCommittee v1 NOT invoked — it requires "
                                             "regime/trend/valuation/volatility context that recorded "
                                             "data cannot supply; defaults would fabricate opinions",
                         "authorizes_execution": False,
                         "next_step": "Owner review; import marked prices + history before any proposal"})


def skeptic(ctx: dict) -> dict:
    prior = ctx.get("prior", [])
    stale = [g for p in prior for g in p["output"].get("gaps", []) if "old" in g or "history" in g]
    return _result("complete", f"Skeptic: {len(stale)} data-quality objection(s)",
                   findings=[f"Objection: {s}" for s in stale[:6]] or ["No data-quality objections found"])


def saathi_report(ctx: dict) -> dict:
    prior = ctx.get("prior", [])
    done = sum(1 for p in prior if p["output"].get("status") == "complete")
    awaiting = [p["role_name"] for p in prior if p["output"].get("status") == "awaiting_evidence"]
    errors = [p["role_name"] for p in prior if p["output"].get("status") == "error"]
    gaps = sorted({g for p in prior for g in p["output"].get("gaps", [])})
    return _result("complete",
                   f"{done}/{len(prior)} steps complete; {len(awaiting)} awaiting evidence; {len(errors)} errors",
                   findings=[f"{p['role_name']}: {p['output'].get('summary')}" for p in prior],
                   gaps=gaps,
                   data={"awaiting_evidence": awaiting, "errors": errors})


def system_health(ctx: dict) -> dict:
    from saathi.organization.system_status import system_status
    rows = system_status(force=True)["systems"]
    bad = [r for r in rows if r["status"] not in ("OK",)]
    return _result("complete", f"{len(rows) - len(bad)}/{len(rows)} systems OK",
                   findings=[f"{r['name']}: {r['status']} — {r['detail']}" for r in rows],
                   gaps=[f"{r['name']} is {r['status']}" for r in bad])


def evidence_audit(ctx: dict) -> dict:
    from saathi.evidence.store import default_store
    s = default_store().stats()
    return _result("complete", "Evidence Service statistics read",
                   findings=[f"{k}: {v}" for k, v in list(s.items())[:6]],
                   evidence=[{"source": "evidence_service", "ref": "stats", "detail": "read-only"}])


PROBES: dict[str, Callable[[dict], dict]] = {
    f.__name__: f for f in (
        paper_portfolio, exposure, concentration, crypto_market_data, nepse_market_snapshot,
        nepse_sector, nepse_swing, governed_research, source_freshness, guardian_posture,
        risk_budget_check, stress_engine, compliance_posture, desk_digest, challenge_gaps,
        fund_manager_synthesis, committee_synthesis, skeptic, saathi_report, system_health,
        evidence_audit)
}


def run_probe(name: str, ctx: dict[str, Any]) -> dict:
    fn = PROBES.get(name)
    if fn is None:
        return _result("error", f"Unknown probe {name}")
    try:
        out = fn(ctx)
    except Exception as exc:
        return _result("error", f"{name} failed: {type(exc).__name__}",
                       gaps=[f"{type(exc).__name__}: {str(exc)[:160]}"])
    out["llm_used"] = False
    return out
