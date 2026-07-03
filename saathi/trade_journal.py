"""Investment Memory & Trade Journal (M5 Phase 6) — financial Platform Memory.

The permanent, append-only record of every capital-allocation decision — the
financial equivalent of Platform Memory. A journal is NEVER deleted or rewritten;
it captures exactly what the system believed at the time (Decision Snapshot) and
the market it believed it in (Market Context Snapshot), so future analysis stays
honest even after the algorithms improve.

Learning consumes journals, not raw executions:
    Execution → Trade Journal → Investment Learning → Knowledge Promotion (M2)

Every closed trade carries structured Lessons (Observation / Root Cause /
Recommendation / Confidence / Capabilities / Evidence — the same shape as the
Learning Runtime), plus Strategy / Research / Portfolio attribution so months
later you can answer "which strategy actually works?" and "which research signals
are predictive?" — not just "did BTC make money?".

Deterministic (AP-17); clock / publisher / recorder / db path injected (AP-12).
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class ExitReason(str, Enum):
    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    MANUAL = "manual"
    TIME_EXIT = "time_exit"
    RISK_EXIT = "risk_exit"
    STRATEGY_CHANGE = "strategy_change"
    REBALANCE = "rebalance"


class Strategy(str, Enum):
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    FUNDAMENTAL = "fundamental"
    AI_DISCOVERY = "ai_discovery"
    MANUAL_OVERRIDE = "manual_override"
    RESEARCH_DRIVEN = "research_driven"


@dataclass
class DecisionSnapshot:
    """Exactly what the system believed at decision time — frozen forever."""
    opportunity_score: float = 0.0
    research_confidence: float = 0.0
    risk_score: float = 0.0
    simulation_ev_usd: float = 0.0
    expected_return: float = 0.0
    capital_allocation: str = ""
    portfolio_health_before: float = 0.0
    executive_recommendation: str = ""


@dataclass
class MarketContext:
    btc_dominance: float = 0.0
    fear_greed: float = 0.0          # 0..100
    vix: float = 0.0
    interest_rate: float = 0.0
    stablecoin_inflows_usd: float = 0.0
    regime: str = "unknown"          # bull / bear / chop
    news: list[str] = field(default_factory=list)


@dataclass
class ResearchAttribution:
    """Per-agent scores at decision time — lets the Research Dept reweight."""
    fundamentals: float = 0.0
    technical: float = 0.0
    onchain: float = 0.0
    sentiment: float = 0.0
    team_github: float = 0.0
    risk: float = 0.0


@dataclass
class PortfolioAttribution:
    health_before: float = 0.0
    health_after: float = 0.0
    risk_delta: float = 0.0
    cash_delta: float = 0.0
    diversification_delta: float = 0.0


@dataclass
class Lesson:
    observation: str
    root_cause: str = ""
    recommendation: str = ""
    confidence: float = 0.5
    capabilities_affected: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class TradeJournal:
    journal_id: str
    case_id: str
    intent_id: str
    broker: str
    asset: str
    asset_class: str
    strategy: Strategy
    quantity: float
    entry_price: float
    position_size_usd: float
    fees_usd: float
    opened_at: float
    status: TradeStatus = TradeStatus.OPEN
    exit_price: float = 0.0
    exit_reason: ExitReason | None = None
    closed_at: float = 0.0
    duration_s: float = 0.0
    pnl_usd: float = 0.0
    return_pct: float = 0.0
    decision: DecisionSnapshot = field(default_factory=DecisionSnapshot)
    market: MarketContext = field(default_factory=MarketContext)
    research: ResearchAttribution = field(default_factory=ResearchAttribution)
    portfolio: PortfolioAttribution = field(default_factory=PortfolioAttribution)
    lessons: list[Lesson] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def is_win(self) -> bool:
        return self.status is TradeStatus.CLOSED and self.pnl_usd > 0


# ── Registry (append-only; the financial Platform Memory) ───────────────────
class TradeJournalRegistry:
    def __init__(self, db_path: "str | Path", *, now: Callable[[], float] = None,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        import time
        self.path = str(db_path)
        self.now = now or time.time
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS journals (
                journal_id TEXT PRIMARY KEY,
                case_id TEXT, intent_id TEXT, asset TEXT, asset_class TEXT,
                strategy TEXT, status TEXT,
                pnl_usd REAL, return_pct REAL,
                opened_at REAL, closed_at REAL,
                payload TEXT
            );
        """)
        self._db.commit()
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    def record_open(self, order, *, strategy: Strategy,
                    decision: DecisionSnapshot | None = None,
                    market: MarketContext | None = None,
                    research: ResearchAttribution | None = None,
                    portfolio_health_before: float = 0.0,
                    tags: list[str] | None = None) -> TradeJournal:
        """Open a journal from a FILLED ExecutionOrder. Append-only."""
        intent = order.intent
        j = TradeJournal(
            journal_id=str(uuid.uuid4()), case_id=intent.case_id,
            intent_id=intent.intent_id, broker=intent.broker, asset=intent.symbol,
            asset_class=intent.asset_class.value, strategy=strategy,
            quantity=order.filled_quantity, entry_price=order.avg_price,
            position_size_usd=order.notional_usd, fees_usd=order.fee_usd,
            opened_at=self.now(),
            decision=decision or DecisionSnapshot(portfolio_health_before=portfolio_health_before),
            market=market or MarketContext(),
            research=research or ResearchAttribution(),
            portfolio=PortfolioAttribution(health_before=portfolio_health_before),
            tags=tags or [])
        self._write(j)
        self._publish("trade.opened", {"journal_id": j.journal_id, "asset": j.asset,
                                       "size_usd": j.position_size_usd})
        return j

    def record_close(self, journal_id: str, *, exit_price: float,
                     exit_reason: ExitReason, exit_fees_usd: float = 0.0,
                     portfolio: PortfolioAttribution | None = None,
                     lessons: list[Lesson] | None = None) -> TradeJournal:
        j = self.get(journal_id)
        if j is None:
            raise KeyError(f"journal {journal_id} not found")
        if j.status is TradeStatus.CLOSED:
            raise ValueError("a journal is immutable once closed — cannot re-close")
        now = self.now()
        j.exit_price = exit_price
        j.exit_reason = exit_reason
        j.closed_at = now
        j.duration_s = round(now - j.opened_at, 3)
        j.fees_usd = round(j.fees_usd + exit_fees_usd, 2)
        j.pnl_usd = round((exit_price - j.entry_price) * j.quantity - j.fees_usd, 2)
        j.return_pct = round(j.pnl_usd / j.position_size_usd, 4) if j.position_size_usd else 0.0
        j.status = TradeStatus.CLOSED
        if portfolio is not None:
            j.portfolio = portfolio
        if lessons:
            j.lessons = lessons
        self._write(j)
        self._publish("trade.closed", {
            "journal_id": j.journal_id, "asset": j.asset, "pnl_usd": j.pnl_usd,
            "return_pct": j.return_pct, "exit": exit_reason.value})
        self._episode(
            agent="trade_journal", department="investment", product="journal",
            intent="trade_closed",
            action=f"closed {j.asset} ({j.strategy.value}) via {exit_reason.value}",
            result=f"PnL ${j.pnl_usd:.0f} ({j.return_pct:+.1%})",
            outcome="success" if j.is_win else "failure",
            quality_score=round(max(0.0, min(1.0, 0.5 + j.return_pct)), 3),
            metadata={"journal_id": j.journal_id, "strategy": j.strategy.value,
                      "asset_class": j.asset_class, "exit_reason": exit_reason.value,
                      "lessons": [asdict(l) for l in j.lessons]})
        return j

    def get(self, journal_id: str) -> TradeJournal | None:
        row = self._db.execute("SELECT payload FROM journals WHERE journal_id=?",
                               (journal_id,)).fetchone()
        return _decode(json.loads(row[0])) if row else None

    def all(self, status: TradeStatus | None = None) -> list[TradeJournal]:
        if status is None:
            rows = self._db.execute("SELECT payload FROM journals").fetchall()
        else:
            rows = self._db.execute("SELECT payload FROM journals WHERE status=?",
                                    (status.value,)).fetchall()
        return [_decode(json.loads(r[0])) for r in rows]

    def closed(self) -> list[TradeJournal]:
        return self.all(TradeStatus.CLOSED)

    def _write(self, j: TradeJournal) -> None:
        self._db.execute(
            "INSERT INTO journals (journal_id,case_id,intent_id,asset,asset_class,"
            "strategy,status,pnl_usd,return_pct,opened_at,closed_at,payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(journal_id) DO UPDATE SET status=excluded.status,"
            "pnl_usd=excluded.pnl_usd,return_pct=excluded.return_pct,"
            "closed_at=excluded.closed_at,payload=excluded.payload",
            (j.journal_id, j.case_id, j.intent_id, j.asset, j.asset_class,
             j.strategy.value, j.status.value, j.pnl_usd, j.return_pct,
             j.opened_at, j.closed_at, _encode(j)))
        self._db.commit()


def _encode(j: TradeJournal) -> str:
    d = asdict(j)
    d["strategy"] = j.strategy.value
    d["status"] = j.status.value
    d["exit_reason"] = j.exit_reason.value if j.exit_reason else None
    return json.dumps(d)


def _decode(d: dict) -> TradeJournal:
    d = dict(d)
    d["strategy"] = Strategy(d["strategy"])
    d["status"] = TradeStatus(d["status"])
    d["exit_reason"] = ExitReason(d["exit_reason"]) if d.get("exit_reason") else None
    d["decision"] = DecisionSnapshot(**d.get("decision", {}))
    d["market"] = MarketContext(**d.get("market", {}))
    d["research"] = ResearchAttribution(**d.get("research", {}))
    d["portfolio"] = PortfolioAttribution(**d.get("portfolio", {}))
    d["lessons"] = [Lesson(**l) for l in d.get("lessons", [])]
    return TradeJournal(**d)


# ── Performance Analytics (Executive Intelligence consumes this) ────────────
@dataclass
class PerformanceReport:
    trades: int
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    expectancy_usd: float
    profit_factor: float
    sharpe: float
    max_drawdown_usd: float
    avg_holding_s: float
    total_pnl_usd: float
    best_strategy: str | None
    worst_strategy: str | None
    best_asset_class: str | None
    worst_asset_class: str | None

    def render(self) -> str:
        return (f"📊 {self.trades} trades · win {self.win_rate:.0%} · "
                f"expectancy ${self.expectancy_usd:.0f} · PF {self.profit_factor:.2f} · "
                f"Sharpe {self.sharpe:.2f} · maxDD ${self.max_drawdown_usd:.0f} · "
                f"best {self.best_strategy}")


class PerformanceAnalytics:
    def analyze(self, journals: list[TradeJournal]) -> PerformanceReport:
        closed = [j for j in journals if j.status is TradeStatus.CLOSED]
        if not closed:
            return PerformanceReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None, None, None, None)
        wins = [j.pnl_usd for j in closed if j.pnl_usd > 0]
        losses = [j.pnl_usd for j in closed if j.pnl_usd <= 0]
        n = len(closed)
        win_rate = round(len(wins) / n, 4)
        avg_win = round(statistics.mean(wins), 2) if wins else 0.0
        avg_loss = round(statistics.mean(losses), 2) if losses else 0.0
        expectancy = round(win_rate * avg_win + (1 - win_rate) * avg_loss, 2)
        profit_factor = round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else float("inf") if wins else 0.0
        rets = [j.return_pct for j in closed]
        sharpe = round(statistics.mean(rets) / statistics.pstdev(rets), 3) if len(rets) > 1 and statistics.pstdev(rets) else 0.0
        max_dd = self._max_drawdown([j for j in sorted(closed, key=lambda x: x.closed_at)])
        avg_hold = round(statistics.mean([j.duration_s for j in closed]), 1)
        total_pnl = round(sum(j.pnl_usd for j in closed), 2)
        best_strat, worst_strat = self._best_worst(closed, lambda j: j.strategy.value)
        best_ac, worst_ac = self._best_worst(closed, lambda j: j.asset_class)
        return PerformanceReport(n, win_rate, avg_win, avg_loss, expectancy,
                                 profit_factor, sharpe, max_dd, avg_hold, total_pnl,
                                 best_strat, worst_strat, best_ac, worst_ac)

    @staticmethod
    def _max_drawdown(ordered: list[TradeJournal]) -> float:
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for j in ordered:
            equity += j.pnl_usd
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return round(max_dd, 2)

    @staticmethod
    def _best_worst(closed, key) -> tuple[str | None, str | None]:
        totals: dict[str, float] = {}
        for j in closed:
            totals[key(j)] = totals.get(key(j), 0.0) + j.pnl_usd
        if not totals:
            return None, None
        best = max(totals, key=totals.get)
        worst = min(totals, key=totals.get)
        return best, worst

    def research_attribution(self, journals: list[TradeJournal]) -> dict:
        """Average per-agent research score for winners vs losers — this is what
        lets the Research Department automatically improve its weighting."""
        closed = [j for j in journals if j.status is TradeStatus.CLOSED]
        winners = [j for j in closed if j.is_win]
        losers = [j for j in closed if not j.is_win]
        cats = ("fundamentals", "technical", "onchain", "sentiment", "team_github", "risk")

        def avg(group, cat):
            vals = [getattr(j.research, cat) for j in group]
            return round(statistics.mean(vals), 1) if vals else 0.0

        return {cat: {"winners": avg(winners, cat), "losers": avg(losers, cat)}
                for cat in cats}
