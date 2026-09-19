"""Standing duties — the recurring, real work each logical role performs.

Every duty is a deterministic READ-ONLY check against a real SaathiOS source
(stores, logs, posture, evidence). A role with no usable source still has a
duty: it re-verifies what is missing and reports AWAITING_EVIDENCE with the
reason, so the owner can see exactly why that desk cannot work yet.

Duties never call a model, never write outside their return value, never call
the ExecutionGateway, never place/approve anything.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from saathi.organization import probes as P

ROOT = Path(__file__).resolve().parent.parent.parent
_r = P._result


def _data(*parts) -> Path:
    """Data root is overridable (tests / isolated validation); default repo data/."""
    if parts == ("platform", "platform.db"):
        return P._platform_db()
    base = os.environ.get("SAATHI_ORG_DATA_ROOT")
    return (Path(base) if base else ROOT / "data").joinpath(*parts)


def _count(db: Path, sql: str, args=()) -> int | None:
    if not db.exists():
        return None
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3)
    try:
        return c.execute(sql, args).fetchone()[0]
    finally:
        c.close()


def _rows(db: Path, sql: str, args=()) -> list[dict] | None:
    if not db.exists():
        return None
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def _missing(what: str, why: str) -> dict:
    return _r("awaiting_evidence", f"No data: {what}", gaps=[why])


# ── engineering ─────────────────────────────────────────────────────────────
def _git(*args) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          timeout=5, check=True).stdout


def eng_git_changes(ctx):
    lines = [x for x in _git("status", "--porcelain").splitlines() if x.strip()]
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    return _r("complete", f"{len(lines)} uncommitted change(s) on {branch}",
              findings=[f"Branch {branch}"] + [f"Changed: {x[3:]}" for x in lines[:6]],
              evidence=[{"source": "git", "ref": branch, "detail": "status --porcelain"}])


def eng_recent_commits(ctx):
    log = _git("log", "-8", "--pretty=%h %ar %s").splitlines()
    return _r("complete", f"Reviewed last {len(log)} commits", findings=log,
              evidence=[{"source": "git", "ref": (log[0].split()[0] if log else ""), "detail": "log -8"}])


def eng_test_inventory(ctx):
    py = len(list((ROOT / "tests").glob("test_*.py")))
    js = len(list((ROOT / "saathi-os" / "lib").glob("*.test.js")))
    return _r("complete", f"{py} Python + {js} JS test files tracked",
              findings=[f"Python test files: {py}", f"Frontend test files: {js}"],
              gaps=["Test runs are not executed by duties (read-only); results come from CI/local runs"])


def eng_error_log(ctx):
    p = _data("local.err.log")
    if not p.exists():
        return _missing("error log", "data/local.err.log not present")
    text = p.read_text(errors="replace").splitlines()[-200:]
    killed = [l for l in text if "Killed: 9" in l]
    errors = [l for l in text if "Error" in l or "Traceback" in l]
    gaps = []
    if killed:
        gaps.append(f"Backend process killed (SIGKILL) {len(killed)}× in recent log — likely memory pressure")
    return _r("complete", f"{len(killed)} kill(s), {len(errors)} error line(s) in recent backend log",
              findings=[l[-160:] for l in (killed + errors)[-4:]] or ["No recent errors"], gaps=gaps,
              evidence=[{"source": "log", "ref": "data/local.err.log", "detail": f"modified {P._age(p.stat().st_mtime)} ago"}])


def eng_models(ctx):
    from saathi.m20_console.status import inference_control_center_facet
    f = inference_control_center_facet()
    running = sorted({e.get("engine_id") for e in f.get("engines", []) if e.get("running")})
    gaps = []
    free = f.get("hardware_available_gb")
    if isinstance(free, (int, float)) and free < 2:
        gaps.append(f"Only {free} GB memory free — keep model inference to one small job at a time")
    return _r("complete", f"{f.get('models_installed_count', 0)} local models; engines: {', '.join(running) or 'none'}",
              findings=[f"Governed gateway {'on' if f.get('gateway_enabled') else 'off'}",
                        f"Cloud fallback {'on' if f.get('cloud_fallback') else 'off'}"], gaps=gaps,
              evidence=[{"source": "inference_status", "ref": f.get("schema_version"), "detail": "facet"}])


def eng_security(ctx):
    # Baseline file only: the live release gate records evidence (a write), so a
    # read-only duty must not call it.
    from saathi.security.redteam.baseline import load as load_baseline
    base = load_baseline() or {}
    if not base:
        return _missing("red-team baseline", "No red-team baseline has been generated")
    t = base.get("totals") or {}
    gen = base.get("generated_at", "")
    vulns = t.get("confirmed_vulnerabilities", 0)
    return _r("complete", f"Red-team baseline: {t.get('boundaries_held')}/{t.get('attacks')} boundaries held, "
                          f"{vulns} confirmed vuln(s)",
              findings=[f"Release-blocking: {t.get('release_blocking', 0)}"],
              gaps=[f"Baseline generated {gen} — re-run the red-team suite to refresh"] if gen else [],
              evidence=[{"source": "security.redteam.baseline", "ref": gen, "detail": "read-only"}])


def eng_access_audit(ctx):
    n = _count(_data("platform", "platform.db"), "SELECT COUNT(*) FROM audit_events")
    recent = _count(_data("platform", "platform.db"),
                    "SELECT COUNT(*) FROM audit_events WHERE ts > ?", (time.time() - 86400,))
    if n is None:
        return _missing("audit events", "platform.db not present")
    return _r("complete", f"{n} audit events recorded, {recent} in last 24 h",
              evidence=[{"source": "platform_audit", "ref": "audit_events", "detail": "count"}])


def eng_prompts(ctx):
    try:
        from saathi import ai_lab
        items = ai_lab.list_prompts() if hasattr(ai_lab, "list_prompts") else None
    except Exception:
        items = None
    if items is None:
        return _missing("prompt registry listing", "AI Lab exposes no read-only prompt listing to duties")
    return _r("complete", f"{len(items)} prompts in the AI Lab registry")


# ── operations / business ───────────────────────────────────────────────────
def biz_runtime_queue(ctx):
    from saathi.agent_runtime.store import DB_PATH
    db = Path(DB_PATH)
    rows = _rows(db, "SELECT state, COUNT(*) AS n FROM orchestration_run GROUP BY state")
    if rows is None:
        return _missing("agent runtime store", "agent_runtime.db not present")
    by = {r["state"]: r["n"] for r in rows}
    stale = _count(db, "SELECT COUNT(*) FROM orchestration_run WHERE state IN ('queued','created','planning') "
                       "AND updated_at < ?", (time.time() - 6 * 3600,))
    gaps = [f"{stale} queued run(s) untouched for > 6 h (stale)"] if stale else []
    return _r("complete", f"Agent runtime: {sum(by.values())} runs · " + ", ".join(f"{k} {v}" for k, v in by.items()),
              gaps=gaps, evidence=[{"source": "agent_runtime", "ref": "orchestration_run", "detail": "states"}])


def biz_workflows(ctx):
    n = _count(_data("platform", "platform.db"), "SELECT COUNT(*) FROM workflow_plans")
    if n is None:
        return _missing("workflow plans", "platform.db not present")
    if n == 0:
        return _missing("workflow plans", "No workflow plans recorded yet")
    return _r("complete", f"{n} workflow plan(s)")


def biz_revenue(ctx):
    n = _count(_data("revenue.db"), "SELECT COUNT(*) FROM revenue")
    if not n:
        return _missing("revenue", "No revenue entries recorded (data/revenue.db empty)")
    total = _rows(_data("revenue.db"), "SELECT currency, SUM(amount) AS s FROM revenue GROUP BY currency")
    return _r("complete", f"{n} revenue entries", findings=[f"{t['currency']}: {t['s']:.2f}" for t in total])


def biz_budget(ctx):
    n = _count(_data("ceo_os.db"), "SELECT COUNT(*) FROM budget")
    if not n:
        return _missing("budgets", "No budgets recorded in CEO OS")
    return _r("complete", f"{n} budget line(s)")


def biz_ledger(ctx):
    n = _count(_data("ceo_os.db"), "SELECT COUNT(*) FROM financial_entry")
    if not n:
        return _missing("financial entries", "No financial entries recorded in CEO OS")
    return _r("complete", f"{n} financial entr(ies)")


def biz_forecast(ctx):
    n = _count(_data("revenue.db"), "SELECT COUNT(*) FROM revenue") or 0
    if n < 12:
        return _missing("forecast history", f"{n} revenue observations; forecasting needs ≥ 12")
    return _r("complete", "Sufficient history for a forecast")


def biz_studio(ctx):
    n = _count(_data("studio_os.db"), "SELECT COUNT(*) FROM project")
    if not n:
        return _missing("product projects", "No Studio projects recorded")
    return _r("complete", f"{n} Studio project(s)")


def biz_growth(ctx):
    p = _data("autopost_log.json")
    if not p.exists():
        return _missing("posting log", "autopost_log.json not present")
    log = json.loads(p.read_text() or "{}")
    days = sorted(log.keys())[-7:]
    ok = err = 0
    errs = set()
    for d in days:
        for slot in (log[d] or {}).values():
            for platform, res in ((slot or {}).get("results") or {}).items():
                if res == "posted":
                    ok += 1
                else:
                    err += 1
                    errs.add(platform)
    gaps = [f"Posting failing on: {', '.join(sorted(errs))}"] if errs else []
    return _r("complete", f"Last {len(days)} day(s): {ok} posts succeeded, {err} failed",
              findings=[f"Days covered: {', '.join(days)}"], gaps=gaps,
              evidence=[{"source": "autopost_log", "ref": days[-1] if days else "", "detail": "results"}])


def biz_digest(ctx):
    return _digest(ctx, "Business & operations")


# ── personal ────────────────────────────────────────────────────────────────
def personal_notifications(ctx):
    rows = _rows(_data("platform", "platform.db"),
                 "SELECT severity, COUNT(*) AS n FROM notifications WHERE read=0 AND archived=0 GROUP BY severity")
    if rows is None:
        return _missing("notifications", "platform.db not present")
    total = sum(r["n"] for r in rows)
    return _r("complete", f"{total} unread notification(s)",
              findings=[f"{r['severity']}: {r['n']}" for r in rows])


def personal_learning(ctx):
    rows = _rows(_data("coach.db"), "SELECT skill, band, ts FROM coach_sessions ORDER BY ts DESC LIMIT 5")
    ielts = _count(_data("platform", "platform.db"), "SELECT COUNT(*) FROM ielts_records")
    if not rows and not ielts:
        return _missing("learning records", "No coach sessions or IELTS records")
    f = [f"{r['skill']}: band {r['band']}" for r in (rows or [])]
    gaps = []
    if rows:
        last = max(float(r["ts"] or 0) for r in rows)
        if time.time() - last > 3 * 86400:
            gaps.append(f"Last practice session {P._age(last)} ago")
    return _r("complete", f"{len(rows or [])} recent coach session(s), {ielts or 0} IELTS record(s)",
              findings=f, gaps=gaps)


def personal_conversations(ctx):
    rows = _rows(_data("chat.db"), "SELECT COUNT(*) AS n, MAX(created_at) AS last FROM message")
    if not rows:
        return _missing("conversations", "chat.db not present")
    n, last = rows[0]["n"], rows[0]["last"]
    return _r("complete", f"{n} chat message(s); last {P._age(float(last)) + ' ago' if last else 'never'}")


def personal_goals(ctx):
    from saathi.ceo.store import default_store
    goals = default_store().list_goals("ajay")
    if not goals:
        return _missing("life goals", "No goals recorded in CEO OS — add goals to plan against")
    return _r("complete", f"{len(goals)} goal(s) tracked", findings=[g.get("description", "") for g in goals[:5]])


def personal_docs(ctx):
    n = sum(1 for _ in (ROOT / "docs").rglob("*.md")) if (ROOT / "docs").exists() else 0
    return _r("complete", f"{n} documents in the docs library")


# ── research ────────────────────────────────────────────────────────────────
def research_events(ctx, *, types=None, label="research"):
    from saathi import research_surface
    ev = research_surface.events().get("events", [])
    if types:
        ev = [e for e in ev if e.get("event_type") in types]
    if not ev:
        return _missing(label, "No matching events in the research surface")
    fresh = sum(1 for e in ev if e.get("freshness") == "RECENT")
    return _r("complete", f"{len(ev)} {label} event(s), {fresh} recent",
              findings=[e.get("headline", "") for e in ev[:6]],
              evidence=[{"source": "evidence_service", "ref": (e.get("evidence_refs") or [""])[0],
                         "detail": e.get("source_tier", "")} for e in ev[:5]])


def research_disclosures(ctx):
    return research_events(ctx, types={"DIVIDEND", "BONUS", "RIGHTS", "AGM", "BOOK_CLOSE", "NOTICE",
                                       "CORPORATE_ACTION", "DISCLOSURE", "LISTING"}, label="disclosure")


def research_policy(ctx):
    from saathi import research_surface
    src = (research_surface.health().get("source_health") or {})
    avail = [k for k, v in src.items() if (v or {}).get("status") == "AVAILABLE"]
    unknown = [k for k, v in src.items() if (v or {}).get("status") != "AVAILABLE"]
    return _r("complete" if avail else "awaiting_evidence",
              f"Regulator sources available: {', '.join(avail) or 'none'}",
              gaps=[f"Source status unknown: {', '.join(unknown)}"] if unknown else [])


def research_orchestrator(ctx):
    rows = _rows(_data("platform", "research_orchestrator.db"),
                 "SELECT state, COUNT(*) AS n FROM orch_jobs GROUP BY state")
    if rows is None:
        return _missing("research jobs", "research_orchestrator.db not present")
    by = {r["state"]: r["n"] for r in rows}
    return _r("complete", "Research jobs: " + ", ".join(f"{k} {v}" for k, v in by.items()),
              evidence=[{"source": "research_orchestrator", "ref": "orch_jobs", "detail": "states"}])


def research_lab(ctx):
    rows = _rows(_data("platform", "research_lab.db"),
                 "SELECT name, status FROM rl_experiments ORDER BY created_at DESC LIMIT 5")
    if not rows:
        return _missing("strategy experiments", "No research-lab experiments recorded")
    return _r("complete", f"{len(rows)} recent strategy experiment(s)",
              findings=[f"{r['name']}: {r['status']}" for r in rows],
              gaps=["Backtests are research only — never execution signals"])


def research_evidence_index(ctx):
    from saathi.evidence.store import default_store
    s = default_store().stats()
    return _r("complete", "Evidence index refreshed",
              findings=[f"{k}: {v}" for k, v in list(s.items())[:6]],
              evidence=[{"source": "evidence_service", "ref": "stats", "detail": "read-only"}])


def research_contradictions(ctx):
    from saathi import research_surface
    ev = research_surface.events().get("events", [])
    c = [e for e in ev if e.get("contradiction_state") not in (None, "", "NONE")]
    return _r("complete", f"Checked {len(ev)} events: {len(c)} contradiction(s)",
              findings=[f"{e.get('headline')}: {e.get('contradiction_note')}" for e in c[:5]])


def research_market_data_quality(ctx):
    rows = _rows(_data("platform", "platform.db"),
                 "SELECT quality, COUNT(*) AS n FROM md_bars GROUP BY quality")
    if not rows:
        return _missing("market data", "No bars in the market-data store")
    return _r("complete", "Bar quality: " + ", ".join(f"{r['quality']} {r['n']}" for r in rows))


# ── investment ──────────────────────────────────────────────────────────────
def crypto_feed(ctx):
    enabled = os.getenv("SAATHI_PUBLIC_MARKET_DATA", "").strip().lower() in {"1", "true", "yes", "on"}
    base = P.crypto_market_data(ctx)
    if base["status"] == "complete":
        return base
    why = ("Public crypto market-data feed is enabled but has recorded no bars" if enabled else
           "Public crypto market-data feed is disabled (SAATHI_PUBLIC_MARKET_DATA off)")
    return _missing("crypto market data", why)


def nepse_regime(ctx):
    snap = P.nepse_market_snapshot(ctx)
    if snap["status"] != "complete":
        return snap
    d = snap["data"]
    adv, dec = d["advancing"], d["declining"]
    ratio = adv / max(1, adv + dec)
    regime = "RISK-ON breadth" if ratio > 0.6 else "RISK-OFF breadth" if ratio < 0.4 else "MIXED breadth"
    return _r("complete", f"{regime} ({adv} up / {dec} down, one session)",
              findings=[f"Advance ratio {ratio:.0%}"],
              gaps=["Single-session breadth only — regime needs multi-session history"] + snap["gaps"],
              evidence=snap["evidence"])


def nepse_fundamentals(ctx):
    return _missing("financial statements", "No NEPSE financial-statement dataset is ingested")


def history_depth(ctx):
    return P.nepse_swing(ctx)


def pm_allocation(ctx):
    st = P._paper_state()
    if not st or not st["accounts"]:
        return _missing("paper portfolio", "No paper accounts")
    f = []
    for a in st["accounts"]:
        pos = [p for p in st["positions"] if p["account_id"] == a["id"]]
        invested = sum(float(p["quantity"]) * float(p["avg_cost"]) for p in pos)
        cash = float(a["current_cash"] or 0)
        f.append(f"{a['name']}: {invested / max(1, invested + cash):.1%} invested, {len(pos)} position(s)")
    return _r("complete", "Allocation by account (cost basis)", findings=f)


def pm_performance(ctx):
    st = P._paper_state()
    if not st or not st["accounts"]:
        return _missing("paper portfolio", "No paper accounts")
    rows = _rows(_data("platform", "platform.db"), "SELECT name, starting_cash, realized_pnl FROM paper_accounts")
    return _r("complete", "Realized P&L read from paper ledger",
              findings=[f"{r['name']}: realized {float(r['realized_pnl'] or 0):+.2f} on {float(r['starting_cash']):.0f}"
                        for r in rows or []],
              gaps=["Unrealized P&L needs mark prices (none recorded for held symbols)"])


def risk_liquidity(ctx):
    st = P._paper_state()
    if not st or not st["accounts"]:
        return _missing("paper portfolio", "No paper accounts")
    b = P._budget()
    floor = float(b["min_cash_buffer"])
    f, gaps = [], []
    for a in st["accounts"]:
        pos = [p for p in st["positions"] if p["account_id"] == a["id"]]
        nav = float(a["current_cash"] or 0) + sum(float(p["quantity"]) * float(p["avg_cost"]) for p in pos)
        ratio = float(a["current_cash"] or 0) / max(1, nav)
        f.append(f"{a['name']}: cash {ratio:.1%} of NAV (floor {floor:.0%})")
        if ratio < floor:
            gaps.append(f"{a['name']} below cash buffer")
    return _r("complete", "Cash buffer checked against PortfolioRisk budget", findings=f, gaps=gaps)


def risk_nav_history(ctx):
    return _missing("NAV history", "Drawdown needs recorded NAV history; organization duties do not record NAV")


def ic_bull(ctx):
    recent = ctx.get("recent", {})
    good = [f"{r}: {o.get('summary')}" for r, o in recent.items()
            if o.get("status") == "complete" and r.startswith(("nepse.", "pm.", "risk.", "crypto."))]
    return _r("complete", f"Case for: {len(good)} complete desk input(s)", findings=good[:6],
              gaps=["Argument built only from recorded duty outputs (no model reasoning)"])


def ic_bear(ctx):
    recent = ctx.get("recent", {})
    gaps = sorted({g for r, o in recent.items() if r.startswith(("nepse.", "pm.", "risk.", "crypto."))
                   for g in o.get("gaps", [])})
    return _r("complete", f"Case against: {len(gaps)} open data gap(s)", findings=gaps[:8])


def ic_chair(ctx):
    recent = ctx.get("recent", {})
    inv = {r: o for r, o in recent.items() if r.startswith(("nepse.", "pm.", "risk.", "crypto.", "ic.bull", "ic.bear"))}
    gaps = sorted({g for o in inv.values() for g in o.get("gaps", [])})
    return _r("complete", "Standing proposal: HOLD — gather evidence (not a decision)",
              findings=[f"{len(inv)} desk inputs considered"], gaps=gaps[:8],
              data={"proposal": "HOLD_AND_GATHER_EVIDENCE", "authorizes_execution": False})


# ── digests ─────────────────────────────────────────────────────────────────
def _digest(ctx, label, prefixes=None):
    recent = ctx.get("recent", {})
    scope = {r: o for r, o in recent.items() if not prefixes or r.startswith(prefixes)}
    done = sum(1 for o in scope.values() if o.get("status") == "complete")
    waiting = sum(1 for o in scope.values() if o.get("status") == "awaiting_evidence")
    errs = sum(1 for o in scope.values() if o.get("status") == "error")
    issues = sorted({g for o in scope.values() for g in o.get("gaps", [])})[:6]
    return _r("complete", f"{label}: {done} duties OK, {waiting} awaiting data, {errs} errors",
              findings=issues or ["No open issues"])


def digest_company(ctx):
    return _digest(ctx, "Company")


def digest_investment(ctx):
    return _digest(ctx, "Investment", ("inv.", "crypto.", "nepse.", "pm.", "risk.", "ic."))


def digest_crypto(ctx):
    return _digest(ctx, "Crypto desk", ("crypto.",))


def digest_nepse(ctx):
    return _digest(ctx, "NEPSE desk", ("nepse.",))


def digest_portfolio(ctx):
    return _digest(ctx, "Portfolio", ("pm.",))


def digest_risk(ctx):
    return _digest(ctx, "Risk", ("risk.",))


def digest_research(ctx):
    return _digest(ctx, "Research", ("research.",))


def digest_engineering(ctx):
    return _digest(ctx, "Engineering", ("eng.",))


def digest_personal(ctx):
    return _digest(ctx, "Personal office", ("personal.",))


def gov_strategy(ctx):
    from saathi.ceo.store import default_store
    s = default_store()
    goals, decisions = s.list_goals("ajay"), s.list_decisions("ajay")
    if not goals and not decisions:
        return _missing("strategy inputs", "No goals or decisions recorded in CEO OS")
    return _r("complete", f"{len(goals)} goal(s), {len(decisions)} decision(s) reviewed")


def not_integrated(what):
    def _fn(ctx):
        return _missing(what, f"No {what} source is integrated yet")
    _fn.__name__ = f"not_integrated_{what.replace(' ', '_')}"
    return _fn


# ── roster ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Duty:
    role_id: str
    title: str
    fn: object
    interval_sec: int = 600

    @property
    def is_digest(self) -> bool:
        """Digests summarise their team's latest duties, so they run after them."""
        return getattr(self.fn, "__name__", "").startswith(("digest_", "biz_digest", "ic_"))


_D = Duty
_ROSTER = [
    _D("exec.saathi", "Company-wide status digest", digest_company, 300),
    _D("gov.strategy", "Review goals and decisions", gov_strategy, 1800),
    _D("gov.risk_governance", "Verify risk budget & guardian posture", lambda c: P.risk_budget_check(c), 900),
    _D("gov.compliance", "Verify paper-only posture", lambda c: P.compliance_posture(c), 600),
    _D("gov.audit", "Audit evidence service", lambda c: P.evidence_audit(c), 900),
    _D("gov.ethics", "Policy review queue", not_integrated("policy review queue"), 3600),
    _D("inv.fund_manager", "Portfolio-level digest", digest_investment, 600),
    _D("crypto.lead", "Crypto desk digest", digest_crypto, 900),
    _D("crypto.research", "Check crypto market data", crypto_feed, 1200),
    _D("crypto.technical", "Check crypto bars", crypto_feed, 1200),
    _D("crypto.onchain", "On-chain data", not_integrated("on-chain data provider"), 3600),
    _D("crypto.sentiment", "Sentiment data", not_integrated("social-sentiment provider"), 3600),
    _D("crypto.token", "Token fundamentals", not_integrated("token fundamentals dataset"), 3600),
    _D("crypto.news", "Crypto news", not_integrated("crypto news feed"), 3600),
    _D("crypto.quant", "Review strategy experiments", research_lab, 1800),
    _D("crypto.regime", "Classify crypto regime", crypto_feed, 1800),
    *[_D(f"crypto.{m}", "Mandate data check", crypto_feed, 3600)
      for m in ("intraday", "short_term", "swing", "position", "long_term", "hedge")],
    _D("nepse.lead", "NEPSE desk digest", digest_nepse, 600),
    _D("nepse.company", "Read governed research", lambda c: P.governed_research(c), 900),
    _D("nepse.technical", "NEPSE market snapshot", lambda c: P.nepse_market_snapshot(c), 600),
    _D("nepse.fundamental", "Financial statements", nepse_fundamentals, 3600),
    _D("nepse.sector", "Sector classification", lambda c: P.nepse_sector(c), 1800),
    _D("nepse.news", "NEPSE research events", research_events, 900),
    _D("nepse.disclosure", "Corporate disclosures", research_disclosures, 900),
    _D("nepse.macro", "Regulator source check", research_policy, 1800),
    _D("nepse.regime", "Breadth regime", nepse_regime, 900),
    *[_D(f"nepse.{m}", "Mandate history check", history_depth, 1800)
      for m in ("short_term", "swing", "position", "long_term")],
    _D("pm.manager", "Read paper portfolio", lambda c: P.paper_portfolio(c), 600),
    _D("pm.allocation", "Allocation by account", pm_allocation, 900),
    _D("pm.position", "Position review", lambda c: P.paper_portfolio(c), 900),
    _D("pm.exposure", "Gross exposure vs budget", lambda c: P.exposure(c), 900),
    _D("pm.correlation", "Correlation", not_integrated("return series"), 3600),
    _D("pm.performance", "Realized performance", pm_performance, 1800),
    _D("pm.rebalancing", "Concentration vs budget", lambda c: P.concentration(c), 1800),
    _D("pm.hedging", "Hedge inputs", not_integrated("hedging instruments"), 3600),
    _D("risk.chief", "Risk digest", digest_risk, 600),
    _D("risk.market", "Market risk marks", not_integrated("mark prices for held symbols"), 3600),
    _D("risk.portfolio", "Positions vs risk budget", lambda c: P.risk_budget_check(c), 900),
    _D("risk.liquidity", "Cash buffer check", risk_liquidity, 900),
    _D("risk.concentration", "Concentration check", lambda c: P.concentration(c), 900),
    _D("risk.drawdown", "Drawdown", risk_nav_history, 3600),
    _D("risk.scenario", "Scenario inputs", not_integrated("scenario library"), 3600),
    _D("risk.stress", "Engine stress test", lambda c: P.stress_engine(c), 3600),
    _D("risk.challenger", "Challenge open gaps", lambda c: P.challenge_gaps(
        {"prior": [{"output": o} for o in c.get("recent", {}).values()]}), 900),
    _D("ic.chair", "Standing committee proposal", ic_chair, 900),
    _D("ic.bull", "Case for", ic_bull, 900),
    _D("ic.bear", "Case against", ic_bear, 900),
    _D("ic.skeptic", "Data-quality objections", lambda c: P.skeptic(
        {"prior": [{"output": o} for o in c.get("recent", {}).values()]}), 900),
    _D("ic.risk_rep", "Risk representative view", digest_risk, 1200),
    _D("ic.desk_rep", "Desk representative view", digest_nepse, 1200),
    _D("research.head", "Research digest", digest_research, 600),
    _D("research.librarian", "Index evidence", research_evidence_index, 900),
    _D("research.web", "Governed research evidence", lambda c: P.governed_research(c), 900),
    _D("research.deep", "Research job status", research_orchestrator, 900),
    _D("research.news", "Research events", research_events, 900),
    _D("research.fact_checker", "Contradiction check", research_contradictions, 900),
    _D("research.document", "Document intake", not_integrated("document ingestion"), 3600),
    _D("research.data", "Market-data quality", research_market_data_quality, 1200),
    _D("research.source_verifier", "Source freshness", lambda c: P.source_freshness(c), 900),
    _D("research.macro", "Regulator sources", research_policy, 1800),
    _D("research.economic", "Economic data", not_integrated("economic indicator feed"), 3600),
    _D("research.policy", "Policy sources", research_policy, 1800),
    _D("research.competitive", "Competitor watch", not_integrated("competitor data"), 3600),
    _D("research.trend", "Trend data", not_integrated("trend data"), 3600),
    _D("eng.cto", "Engineering digest", digest_engineering, 600),
    _D("eng.architect", "Recent changes review", eng_recent_commits, 1800),
    _D("eng.planning", "Agent runtime queue", biz_runtime_queue, 1200),
    _D("eng.coding", "Working tree status", eng_git_changes, 900),
    _D("eng.code_review", "Review recent commits", eng_recent_commits, 900),
    _D("eng.test", "Test inventory", eng_test_inventory, 1800),
    _D("eng.debugging", "Scan backend error log", eng_error_log, 600),
    _D("eng.devops", "System probes", lambda c: P.system_health(c), 600),
    _D("eng.deployment", "Release posture", eng_recent_commits, 3600),
    _D("eng.monitoring", "System probes", lambda c: P.system_health(c), 300),
    _D("eng.model_manager", "Local model inventory", eng_models, 1200),
    _D("eng.prompt", "Prompt registry", eng_prompts, 3600),
    _D("eng.model_eval", "Evaluation queue", not_integrated("model evaluation queue"), 3600),
    _D("eng.security", "Security posture", eng_security, 900),
    _D("eng.vulnerability", "Dependency scan", not_integrated("vulnerability scanner"), 3600),
    _D("eng.access_audit", "Audit trail", eng_access_audit, 900),
    _D("biz.coo", "Operations digest", biz_digest, 600),
    _D("biz.operations", "Runtime queue", biz_runtime_queue, 600),
    _D("biz.workflow", "Workflow plans", biz_workflows, 1800),
    _D("biz.scheduling", "Calendar access", not_integrated("calendar connector"), 3600),
    _D("biz.cfo", "Revenue review", biz_revenue, 1800),
    _D("biz.accounting", "Financial entries", biz_ledger, 1800),
    _D("biz.budget", "Budgets", biz_budget, 1800),
    _D("biz.forecasting", "Forecast readiness", biz_forecast, 3600),
    _D("biz.product", "Studio projects", biz_studio, 1800),
    _D("biz.growth", "Social posting results", biz_growth, 900),
    _D("biz.sales", "Sales pipeline", not_integrated("sales pipeline"), 3600),
    _D("biz.support", "Support queue", not_integrated("support ticket source"), 3600),
    _D("personal.ea", "Personal office digest", digest_personal, 600),
    _D("personal.email", "Inbox triage", not_integrated("email connector"), 3600),
    _D("personal.calendar", "Calendar review", not_integrated("calendar connector"), 3600),
    _D("personal.travel", "Travel plans", not_integrated("travel provider"), 3600),
    _D("personal.reminder", "Unread notifications", personal_notifications, 600),
    _D("personal.document", "Docs library", personal_docs, 1800),
    _D("personal.notes", "Conversation activity", personal_conversations, 1200),
    _D("personal.learning", "Learning progress", personal_learning, 1800),
    _D("personal.life_planning", "Goals review", personal_goals, 3600),
]
DUTIES: dict[str, Duty] = {d.role_id: d for d in _ROSTER}


def run_duty(duty: Duty, ctx: dict) -> dict:
    try:
        out = duty.fn(ctx)
    except Exception as exc:
        out = _r("error", f"{duty.title} failed: {type(exc).__name__}",
                 gaps=[f"{type(exc).__name__}: {str(exc)[:160]}"])
    out["llm_used"] = False
    return out
